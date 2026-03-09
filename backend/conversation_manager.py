"""
Conversation Manager for AI Agent Chat Backend (MCP 2026-02)

Manages conversation sessions, middleware lifecycle, and Verkle tree finalization.
Each conversation gets one session with multiple prompt interactions.
Each prompt produces its own Verkle span root (intermediate verifiability).
Conversations produce a session-level root when finalized (combining all prompt roots).

Architecture:
- Conversation = 1 session (multiple prompts)
- Each prompt = 1 agent.run_async() call with its own middleware (produces span roots)
- Conversation finalization = Verkle root of all prompt roots
- Canonical logs saved incrementally per prompt to workflows/ folder
"""

import hashlib
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.agent import MCPServer, AIAgent
from src.integrity import HierarchicalVerkleMiddleware
from src.security import SecurityMiddleware
from src.security.key_management import KeyAuthority
from src.config import get_settings
from src.crypto.verkle import VerkleAccumulator
from src.observability.trace_context import TraceContext

import structlog

logger = structlog.get_logger(__name__)


class Conversation:
    """
    Represents a single conversation (multiple prompts/responses).

    Each prompt gets its own HierarchicalVerkleMiddleware (for per-prompt Verkle root).
    The conversation accumulates prompt roots into a session-level Verkle accumulator.
    Canonical logs are saved incrementally after each prompt.
    """

    def __init__(
        self,
        conversation_id: str,
        mcp_server: MCPServer,
        security_middleware: SecurityMiddleware,
    ):
        self.conversation_id = conversation_id
        self.session_id = f"chat-{conversation_id}"
        self.created_at = datetime.now().isoformat()
        self.messages: list[dict] = []
        self.is_finalized = False

        # Shared MCP server and security middleware
        self.mcp_server = mcp_server
        self.security_middleware = security_middleware

        # Conversation-level Verkle accumulator (accumulates per-prompt session roots)
        self.conversation_accumulator = VerkleAccumulator(f"{self.session_id}_conversation")

        # Track per-prompt integrity results
        self.prompt_roots: list[dict] = []

        # Canonical events accumulated across all prompts
        self.all_canonical_events: list[dict] = []

        # Workflow directory for this conversation
        self.workflow_dir = Path("workflows") / f"workflow_{self.session_id}"

        logger.info(
            "conversation_created",
            conversation_id=conversation_id,
            session_id=self.session_id,
        )

    async def send_prompt(self, prompt: str, trace_context: TraceContext = None) -> dict:
        """
        Send a prompt within this conversation.

        Each prompt creates a fresh middleware -> agent -> run_async cycle.
        The prompt's session root is added to the conversation accumulator.
        Canonical logs are saved incrementally.

        Args:
            prompt: The user prompt text.
            trace_context: Optional W3C Trace Context for distributed trace correlation.

        Returns:
            dict with 'output', 'prompt_root', 'prompt_index'
        """
        if self.is_finalized:
            return {"output": "Error: This conversation has been finalized.", "error": True}

        prompt_index = len(self.prompt_roots)
        prompt_session_id = f"{self.session_id}_prompt{prompt_index}"

        # Record user message
        self.messages.append({
            "role": "user",
            "content": prompt,
            "timestamp": datetime.now().isoformat(),
            "prompt_index": prompt_index,
        })

        # Create fresh middleware for this prompt
        # Use prompt-specific session_id for Verkle integrity, but share the
        # conversation-level session_id in Langfuse so all prompts appear
        # under one session (OTel-compliant: session groups multiple traces).
        middleware = HierarchicalVerkleMiddleware(
            session_id=prompt_session_id,
            langfuse_session_id=self.session_id,
            trace_context=trace_context,
        )

        try:
            llm_client = AIAgent.create_llm_client()
        except Exception as e:
            error_msg = f"Error initializing LLM client: {e}"
            self.messages.append({
                "role": "assistant",
                "content": error_msg,
                "timestamp": datetime.now().isoformat(),
                "prompt_index": prompt_index,
            })
            return {"output": error_msg, "error": True}

        agent = AIAgent(
            integrity_middleware=middleware,
            security_middleware=self.security_middleware,
            mcp_server=self.mcp_server,
            llm_client=llm_client,
        )

        try:
            result = await agent.run_async(prompt=prompt, max_turns=6)
            response_text = result.get("output", "No response generated.")
            integrity_info = result.get("integrity", {})

            # Extract prompt-level root
            prompt_root = integrity_info.get("session_root", "")
            event_count = integrity_info.get("event_count", 0)

            # Add prompt root to conversation accumulator
            if prompt_root:
                self.conversation_accumulator.add_event({
                    "counter": len(self.prompt_roots),
                    "type": "prompt_root",
                    "session_id": prompt_session_id,
                    "prompt_root": prompt_root,
                })

            # Store prompt integrity info
            prompt_info = {
                "prompt_index": prompt_index,
                "prompt_session_id": prompt_session_id,
                "prompt_root": prompt_root,
                "event_accumulator_root": integrity_info.get("event_accumulator_root", ""),
                "span_roots": integrity_info.get("span_roots", {}),
                "event_count": event_count,
                "timestamp": datetime.now().isoformat(),
            }
            self.prompt_roots.append(prompt_info)

            # Accumulate canonical events
            prompt_canonical_events = []
            if hasattr(middleware, "canonical_events"):
                prompt_canonical_events = middleware.canonical_events
                self.all_canonical_events.extend(prompt_canonical_events)

            # Compute per-prompt canonical log hash
            prompt_log_text = json.dumps(
                prompt_canonical_events, separators=(",", ":"), sort_keys=True
            )
            prompt_canonical_log_hash = hashlib.sha256(prompt_log_text.encode("utf-8")).hexdigest()
            prompt_info["canonical_log_hash"] = prompt_canonical_log_hash

            # Save canonical log incrementally
            self._save_incremental_log(middleware, prompt_index)

        except Exception as e:
            response_text = f"Error running agent: {e}"
            prompt_canonical_log_hash = None
            self.prompt_roots.append({
                "prompt_index": prompt_index,
                "prompt_session_id": prompt_session_id,
                "prompt_root": None,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            })

        # Record assistant message
        self.messages.append({
            "role": "assistant",
            "content": response_text,
            "timestamp": datetime.now().isoformat(),
            "prompt_index": prompt_index,
        })

        return {
            "output": response_text,
            "prompt_root": self.prompt_roots[-1].get("prompt_root"),
            "prompt_index": prompt_index,
            "canonical_log_hash": prompt_canonical_log_hash,
        }

    def _save_incremental_log(self, middleware: HierarchicalVerkleMiddleware, prompt_index: int):
        """Save canonical log incrementally after each prompt."""
        self.workflow_dir.mkdir(parents=True, exist_ok=True)

        # Save full accumulated canonical log (all prompts so far)
        log_path = self.workflow_dir / "canonical_log.json"
        with open(log_path, "w") as f:
            json.dump(self.all_canonical_events, f, indent=2)

        # Save per-prompt canonical log
        prompt_log_path = self.workflow_dir / f"canonical_log_prompt{prompt_index}.json"
        if hasattr(middleware, "canonical_events"):
            with open(prompt_log_path, "w") as f:
                json.dump(middleware.canonical_events, f, indent=2)

        # Save prompt roots so far
        roots_path = self.workflow_dir / "prompt_roots.json"
        with open(roots_path, "w") as f:
            json.dump(self.prompt_roots, f, indent=2)

        # Save metadata
        metadata_path = self.workflow_dir / "metadata.json"
        metadata = {
            "conversation_id": self.conversation_id,
            "session_id": self.session_id,
            "created_at": self.created_at,
            "prompt_count": len(self.prompt_roots),
            "total_events": len(self.all_canonical_events),
            "is_finalized": self.is_finalized,
            "last_updated": datetime.now().isoformat(),
        }
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)

        logger.info(
            "incremental_log_saved",
            workflow_dir=str(self.workflow_dir),
            prompt_index=prompt_index,
            total_events=len(self.all_canonical_events),
        )

    def finalize(self) -> dict:
        """
        Finalize the conversation: compute conversation-level Verkle root.

        Returns:
            dict with conversation_root, prompt_roots, and workflow_dir
        """
        if self.is_finalized:
            return {"error": "Conversation already finalized."}

        # Finalize conversation-level accumulator
        self.conversation_accumulator.finalize()
        conversation_root = self.conversation_accumulator.get_root_b64()

        # Compute canonical log hash
        canonical_log_text = json.dumps(
            self.all_canonical_events, separators=(",", ":"), sort_keys=True
        )
        canonical_log_hash = hashlib.sha256(canonical_log_text.encode("utf-8")).hexdigest()

        # Save final state to workflow dir
        self.workflow_dir.mkdir(parents=True, exist_ok=True)

        commitments_path = self.workflow_dir / "commitments.json"
        # Merge span_roots from all prompts for top-level access
        merged_span_roots = {}
        for pr in self.prompt_roots:
            for span_id, span_root in pr.get("span_roots", {}).items():
                merged_span_roots[span_id] = span_root
        commitments_data = {
            # session_root alias for verify_cli backward compatibility
            "session_root": conversation_root,
            "conversation_root": conversation_root,
            "span_roots": merged_span_roots,
            "prompt_roots": [pr.get("prompt_root") for pr in self.prompt_roots],
            "prompt_details": self.prompt_roots,
            "canonical_log_hash": canonical_log_hash,
            "total_events": len(self.all_canonical_events),
            "prompt_count": len(self.prompt_roots),
            "is_conversation": True,
        }
        with open(commitments_path, "w") as f:
            json.dump(commitments_data, f, indent=2)

        metadata_path = self.workflow_dir / "metadata.json"
        metadata = {
            "conversation_id": self.conversation_id,
            "session_id": self.session_id,
            "created_at": self.created_at,
            "finalized_at": datetime.now().isoformat(),
            "prompt_count": len(self.prompt_roots),
            "message_count": len(self.messages),
            "total_events": len(self.all_canonical_events),
            "is_finalized": True,
            "conversation_root": conversation_root,
            "canonical_log_hash": canonical_log_hash,
        }
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)

        # Save cryptographic parameters (MPK for IBS signature verification)
        settings = get_settings()
        authority = KeyAuthority(
            master_secret_hex=settings.security.master_secret_key
        )
        crypto_params_path = self.workflow_dir / "crypto_params.json"
        crypto_params = {
            "scheme": "IBS-Cha-Cheon-BLS12-381",
            "mpk": authority.export_mpk(),
        }
        with open(crypto_params_path, "w") as f:
            json.dump(crypto_params, f, indent=2)

        logger.info(
            "conversation_finalized",
            conversation_id=self.conversation_id,
            conversation_root=conversation_root,
            prompt_count=len(self.prompt_roots),
            total_events=len(self.all_canonical_events),
        )

        result = {
            "conversation_id": self.conversation_id,
            "session_id": self.session_id,
            "conversation_root": conversation_root,
            "prompt_roots": [pr.get("prompt_root") for pr in self.prompt_roots],
            "canonical_log_hash": canonical_log_hash,
            "workflow_dir": str(self.workflow_dir),
            "message_count": len(self.messages),
            "prompt_count": len(self.prompt_roots),
            "created_at": self.created_at,
            "finalized_at": datetime.now().isoformat(),
        }

        # Mark as finalized only after all operations succeed
        self.is_finalized = True

        return result

    def get_summary(self) -> dict:
        """Return conversation metadata."""
        return {
            "conversation_id": self.conversation_id,
            "session_id": self.session_id,
            "message_count": len(self.messages),
            "prompt_count": len(self.prompt_roots),
            "is_finalized": self.is_finalized,
            "created_at": self.created_at,
        }


class ConversationManager:
    """
    Manages multiple conversations.
    Provides create, get, list, and finalize operations.
    """

    def __init__(self, mcp_server: MCPServer, security_middleware: SecurityMiddleware):
        self.conversations: dict[str, Conversation] = {}
        self.mcp_server = mcp_server
        self.security_middleware = security_middleware

    def create_conversation(self) -> Conversation:
        """Create a new conversation with a unique ID."""
        conversation_id = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        conversation = Conversation(
            conversation_id=conversation_id,
            mcp_server=self.mcp_server,
            security_middleware=self.security_middleware,
        )
        self.conversations[conversation_id] = conversation
        return conversation

    def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """Get an existing conversation by ID."""
        return self.conversations.get(conversation_id)

    def resume_conversation(self, conversation_id: str, db_data: dict, messages: list[dict]) -> Conversation:
        """
        Resume a conversation from a previous server session.

        Reconstructs a Conversation object from database data so that
        new prompts can be sent to it. Prior canonical events and Verkle
        roots are reloaded from disk if available.

        Args:
            conversation_id: The conversation ID to resume.
            db_data: Row from the conversations table.
            messages: Prior messages from the messages table.

        Returns:
            The resumed Conversation object (also cached in self.conversations).
        """
        conv = Conversation(
            conversation_id=conversation_id,
            mcp_server=self.mcp_server,
            security_middleware=self.security_middleware,
        )
        # Restore metadata
        conv.created_at = db_data.get("created_at", conv.created_at)

        # Restore messages
        for msg in messages:
            conv.messages.append({
                "role": msg["role"],
                "content": msg["content"],
                "timestamp": msg.get("timestamp", ""),
                "prompt_index": msg.get("prompt_index", 0),
            })

        # Reload canonical events and prompt roots from disk if available
        workflow_dir = conv.workflow_dir
        canonical_log_path = workflow_dir / "canonical_log.json"
        if canonical_log_path.exists():
            try:
                with open(canonical_log_path) as f:
                    conv.all_canonical_events = json.load(f)
            except Exception as e:
                logger.warning("failed_to_load_canonical_log", error=str(e))

        prompt_roots_path = workflow_dir / "prompt_roots.json"
        if prompt_roots_path.exists():
            try:
                with open(prompt_roots_path) as f:
                    conv.prompt_roots = json.load(f)
            except Exception as e:
                logger.warning("failed_to_load_prompt_roots", error=str(e))

        # Re-populate conversation accumulator with prior prompt roots
        for pr in conv.prompt_roots:
            if pr.get("prompt_root"):
                conv.conversation_accumulator.add_event({
                    "counter": pr.get("prompt_index", 0),
                    "type": "prompt_root",
                    "session_id": pr.get("prompt_session_id", ""),
                    "prompt_root": pr["prompt_root"],
                })

        self.conversations[conversation_id] = conv

        logger.info(
            "conversation_resumed",
            conversation_id=conversation_id,
            messages_restored=len(conv.messages),
            prompt_roots_restored=len(conv.prompt_roots),
            canonical_events_restored=len(conv.all_canonical_events),
        )

        return conv

    def list_conversations(self) -> list[dict]:
        """List all conversations with metadata."""
        return [conv.get_summary() for conv in self.conversations.values()]

    def finalize_conversation(self, conversation_id: str) -> dict:
        """Finalize a conversation and return integrity info."""
        conversation = self.conversations.get(conversation_id)
        if not conversation:
            return {"error": f"Conversation {conversation_id} not found."}
        return conversation.finalize()

    def delete_conversation(self, conversation_id: str) -> dict:
        """
        Delete a conversation from memory and its workflow directory from disk.

        Args:
            conversation_id: The conversation ID to delete.

        Returns:
            dict with 'deleted' key (True/False) and details.
        """
        # Remove from in-memory cache
        conv = self.conversations.pop(conversation_id, None)

        # Determine workflow directory
        session_id = f"chat-{conversation_id}"
        workflow_dir = Path("workflows") / f"workflow_{session_id}"

        # Delete workflow folder
        dir_deleted = False
        if workflow_dir.exists():
            try:
                shutil.rmtree(workflow_dir)
                dir_deleted = True
                logger.info("workflow_dir_deleted", path=str(workflow_dir))
            except Exception as e:
                logger.warning("workflow_dir_delete_failed", path=str(workflow_dir), error=str(e))

        logger.info(
            "conversation_deleted",
            conversation_id=conversation_id,
            was_in_memory=conv is not None,
            workflow_dir_deleted=dir_deleted,
        )

        return {
            "deleted": True,
            "conversation_id": conversation_id,
            "was_in_memory": conv is not None,
            "workflow_dir_deleted": dir_deleted,
        }

    def finalize_all(self) -> list[dict]:
        """Finalize all active (non-finalized) conversations."""
        results = []
        for conv in self.conversations.values():
            if not conv.is_finalized:
                results.append(conv.finalize())
        return results
