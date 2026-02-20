#!/usr/bin/env python3
r"""
Demo: Hierarchical Verkle Middleware with Spans

Shows how to use the HierarchicalVerkleMiddleware to:
1. Organize events into spans (like OpenTelemetry)
2. Compute per-span Verkle roots
3. Compute session-level root
4. Store locally in hierarchical structure
5. Export to OpenTelemetry format for any UI tool

This demo organizes a simple agent workflow into spans:
- Span 1: Initialize MCP protocol
- Span 2: User interaction and prompt
- Span 3: Tool execution
- Span 4: Final response

Each span gets its own Verkle root for fine-grained verification.

Usage:
  .\venv\Scripts\Activate.ps1
  python examples/demo_hierarchical_spans.py

  & .\venv\Scripts\Activate.ps1; examples/demo_hierarchical_spans.py
"""

import sys
import json
import os
from pathlib import Path

# Fix encoding for Windows
os.environ['PYTHONIOENCODING'] = 'utf-8'

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.integrity import HierarchicalVerkleMiddleware

# ANSI Colors
GREEN = "\033[92m"
BLUE = "\033[94m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"


def print_header(title: str) -> None:
    """Print a large header."""
    print(f"\n{BOLD}{BLUE}{'='*80}{RESET}")
    print(f"{BOLD}{BLUE}{title:^80}{RESET}")
    print(f"{BOLD}{BLUE}{'='*80}{RESET}\n")


def print_subheader(title: str) -> None:
    """Print a section header."""
    print(f"\n{BOLD}{CYAN}>> {title}{RESET}")
    print(f"{DIM}{'-'*80}{RESET}\n")


def demo_hierarchical_spans():
    """Demonstrate hierarchical Verkle with spans"""
    
    print_header("HIERARCHICAL VERKLE MIDDLEWARE WITH SPANS DEMO")
    
    print(f"""{CYAN}This demo shows:
  - Organizing events into spans (like OpenTelemetry)
  - Per-span Verkle roots for fine-grained verification
  - Session-level root combining all spans
  - Local dual storage (canonical log + OTel export)
  - Recovery from loss of observability platform{RESET}\n""")
    
    # Initialize hierarchical middleware
    print_subheader("STEP 1: Initialize Middleware")
    
    middleware = HierarchicalVerkleMiddleware()
    print(f"{GREEN}[OK] HierarchicalVerkleMiddleware initialized{RESET}")
    print(f"{GREEN}[OK] Session ID: {middleware.session_id}{RESET}\n")
    
    # Span 1: MCP Initialize
    print_subheader("STEP 2: SPAN 1 - MCP Initialize")
    
    span1_id = middleware.start_span("mcp_initialize")
    print(f"{YELLOW}Span started:{RESET} {span1_id}\n")
    
    middleware.record_event_in_span(
        "mcp_initialize_request",
        {
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {"protocolVersion": "2024-11"}
        },
        signer_id="server"
    )
    print(f"{GREEN}[OK] Recorded: MCP initialize request{RESET}")
    
    middleware.record_event_in_span(
        "mcp_initialize_response",
        {
            "jsonrpc": "2.0",
            "result": {"protocolVersion": "2024-11", "capabilities": {}},
        },
        signer_id="server"
    )
    print(f"{GREEN}[OK] Recorded: MCP initialize response{RESET}\n")
    
    # Span 2: User Interaction
    print_subheader("STEP 3: SPAN 2 - User Interaction")
    
    span2_id = middleware.start_span("user_interaction")
    print(f"{YELLOW}Span started:{RESET} {span2_id}\n")
    
    user_prompt = "Calculate 100 * 5 using available tools"
    middleware.record_event_in_span(
        "user_prompt",
        {"prompt": user_prompt},
        signer_id="server"
    )
    print(f"{GREEN}[OK] Recorded: User prompt{RESET}")
    print(f"  Query: '{user_prompt}'\n")
    
    # Span 3: Tool Execution
    print_subheader("STEP 4: SPAN 3 - Tool Execution")
    
    span3_id = middleware.start_span("tool_execution")
    print(f"{YELLOW}Span started:{RESET} {span3_id}\n")
    
    middleware.record_event_in_span(
        "mcp_tools_call_request",
        {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "calculator",
                "arguments": {"op": "mul", "a": 100, "b": 5}
            }
        },
        signer_id="server"
    )
    print(f"{GREEN}[OK] Recorded: Tool call request (calculator){RESET}")
    
    middleware.record_event_in_span(
        "tool_output",
        {"result": 500, "success": True},
        signer_id="calculator"
    )
    print(f"{GREEN}[OK] Recorded: Tool output (result: 500){RESET}")
    
    # Span 4: Final Response
    print_subheader("STEP 5: SPAN 4 - Final Response")
    
    span4_id = middleware.start_span("final_response")
    print(f"{YELLOW}Span started:{RESET} {span4_id}\n")
    
    final_response = "The answer is 500. The calculation 100 * 5 was successfully computed using the calculator tool."
    middleware.record_event_in_span(
        "model_output",
        {"response": final_response},
        signer_id="server"
    )
    print(f"{GREEN}[OK] Recorded: Final response{RESET}")
    print(f"  Response: '{final_response[:50]}...'\n")
    
    # Finalize
    print_subheader("STEP 6: Finalize with Hierarchical Verkle Roots")
    
    session_root, commitments, canonical_log_bytes = middleware.finalize()
    
    print(f"{GREEN}[OK] Session finalized{RESET}\n")
    print(f"{BOLD}Hierarchical Commitments:{RESET}")
    print(f"  {YELLOW}Session Root:{RESET} {session_root[:40]}...")
    print(f"  {YELLOW}Span Roots:{RESET}")
    for span_id, root in commitments.span_roots.items():
        span_name = middleware.spans[span_id].name
        print(f"    - {span_name:30} {root[:40]}...")
    print(f"  {YELLOW}Event Count:{RESET} {commitments.event_count}")
    print(f"  {YELLOW}Canonical Log Hash:{RESET} {commitments.canonical_log_hash[:40]}...\n")
    
    # Display spans structure
    print_subheader("STEP 7: Spans Structure (OpenTelemetry)")
    
    spans_summary = {
        span_id: {
            "name": span.name,
            "events": span.event_count,
            "duration_ms": span.duration_ms,
            "root": span.verkle_root[:40] + "..."
        }
        for span_id, span in middleware.spans.items()
    }
    
    print(json.dumps(spans_summary, indent=2))
    print()
    
    # Save to local storage
    print_subheader("STEP 8: Save to Local Storage")
    
    session_dir = Path(f"workflow_{middleware.session_id}")
    saved_files = middleware.save_to_local_storage(session_dir)
    
    print(f"{GREEN}[OK] Data saved to local storage:{RESET}")
    print(f"  Base directory: {saved_files['base_dir']}")
    print(f"  - canonical_log.jsonl (events)")
    print(f"  - spans_structure.json (OTel layout)")
    print(f"  - commitments.json (Verkle roots)")
    print(f"  - metadata.json (session metadata)")
    print(f"  - otel_export.json (OpenTelemetry format)")
    print(f"  - RECOVERY.md (recovery instructions)\n")
    
    # Display OTel export
    print_subheader("STEP 9: OpenTelemetry Export Format")
    
    otel_export = middleware.export_to_otel_format()
    
    print(f"{BOLD}Trace Structure:{RESET}")
    print(f"  {YELLOW}Trace ID:{RESET} {otel_export['traceId']}")
    print(f"  {YELLOW}Span Count:{RESET} {len(otel_export['spans'])}\n")
    
    print(f"{BOLD}Spans:{RESET}")
    for span in otel_export['spans']:
        print(f"  - {span['name']:30} ({span['durationMillis']} ms)")
        print(f"    Root: {span['attributes']['local_verkle_root'][:40]}...")
    print()
    
    # Verification information
    print_subheader("STEP 10: Verification Levels")
    
    print(f"""{BOLD}You can now verify this workflow at multiple levels:{RESET}

{YELLOW}Level 1: Quick Metadata Check{RESET}
  Command: python verify_cli check metadata {session_dir}/metadata.json
  Time: <1 second
  Method: Just check stored metadata

{YELLOW}Level 2: Local Verification{RESET}
  Command: python verify_cli verify local {session_dir} '{session_root}'
  Time: ~100ms
  Method: Reconstruct Verkle roots from local canonical log

{YELLOW}Level 3: Deep Verification (Per-Span){RESET}
  Command: python verify_cli verify --deep local {session_dir} '{session_root}'
  Time: ~500ms
  Method: Verify each span's Verkle root, then verify session root

{YELLOW}Level 4: Cross-Verify with OTel Backend {RESET}
  Command: python verify_cli verify --compare-otel local {session_dir} langfuse:trace-xxx
  Time: Varies
  Method: Compare local structure with OTel UI tool

{CYAN}Key Benefits:{RESET}
  [OK] If Langfuse deleted: Still have complete proof locally
  [OK] If local deleted: Can restore from Langfuse OTel export
  [OK] Any OTel UI tool: Can visualize using otel_export.json
  [OK] Hierarchical: Verify at span level or session level
  [OK] Standards-compliant: OpenTelemetry format for compatibility
""")
    
    # Summary
    print_subheader("SUMMARY")
    
    print(f"""{GREEN}Hierarchical Verkle Middleware Demo Complete!{RESET}

{BOLD}What happened:{RESET}
  - Created 4 spans representing different workflow phases
  - Added {commitments.event_count} events across spans
  - Computed per-span Verkle roots (V1, V2, V3, V4)
  - Computed session-level root from span roots
  - Saved locally in hierarchical structure
  - Exported to OpenTelemetry format for UI tools

{BOLD}Features demonstrated:{RESET}
  [OK] Fine-grained span organization (like OTel)
  [OK] Hierarchical Verkle commitments (multi-level proof)
  [OK] Local dual storage (immutable + OTel format)
  [OK] Recovery from data loss
  [OK] Multi-level verification strategy
  [OK] Standards compliance (RFC 8785 + OpenTelemetry)

{BOLD}Next steps:{RESET}
  1. Verify with: python verify_cli verify local {session_dir} '{session_root}'
  2. Send OTel export to Langfuse/Jaeger for visualization
  3. Keep local directory as source of truth
  4. Share metadata.json for external auditing

{CYAN}Session Root: {session_root}{RESET}
{CYAN}Saved to: {session_dir}{RESET}
""")


if __name__ == "__main__":
    demo_hierarchical_spans()
