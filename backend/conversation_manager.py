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
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.agent import MCPServer, AIAgent
from src.integrity import HierarchicalVerkleMiddleware
from src.security import SecurityMiddleware
from src.crypto.verkle import VerkleAccumulator

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

    async def send_prompt(self, prompt: str) -> dict:
        """
        Send a prompt within this conversation.

        Each prompt creates a fresh middleware -> agent -> run_async cycle.
        The prompt's session root is added to the conversation accumulator.
        Canonical logs are saved incrementally.

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
        middleware = HierarchicalVerkleMiddleware(session_id=prompt_session_id)

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
            if hasattr(middleware, "canonical_events"):
                self.all_canonical_events.extend(middleware.canonical_events)

            # Save canonical log incrementally
            self._save_incremental_log(middleware, prompt_index)

        except Exception as e:
            response_text = f"Error running agent: {e}"
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

        self.is_finalized = True

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

        logger.info(
            "conversation_finalized",
            conversation_id=self.conversation_id,
            conversation_root=conversation_root,
            prompt_count=len(self.prompt_roots),
            total_events=len(self.all_canonical_events),
        )

        return {
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

    def list_conversations(self) -> list[dict]:
        """List all conversations with metadata."""
        return [conv.get_summary() for conv in self.conversations.values()]

    def finalize_conversation(self, conversation_id: str) -> dict:
        """Finalize a conversation and return integrity info."""
        conversation = self.conversations.get(conversation_id)
        if not conversation:
            return {"error": f"Conversation {conversation_id} not found."}
        return conversation.finalize()

    def finalize_all(self) -> list[dict]:
        """Finalize all active (non-finalized) conversations."""
        results = []
        for conv in self.conversations.values():
            if not conv.is_finalized:
                results.append(conv.finalize())
        return results
