#!/usr/bin/env python
r"""
Test Suite Runner

Executes all 158 unit tests across Phase 1-3 features.

USAGE:
------
# One-liner (Windows PowerShell):
& .\venv\Scripts\Activate.ps1; python run_all_tests.py

# Or step by step:
& .\venv\Scripts\Activate.ps1
python run_all_tests.py

# Or run specific test suites:
python -m pytest tests/test_kzg.py -v
python -m pytest tests/test_integrity.py -v
"""

import subprocess
import sys
import io

# Fix Windows terminal encoding
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Color codes
GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"
BOLD = "\033[1m"


def run_pytest(test_file: str, description: str, count: int) -> tuple[bool, int]:
    """Run pytest on a specific test file."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", test_file, "-v", "--tb=short"],
        capture_output=False,
        text=True
    )
    return result.returncode == 0, result.returncode


def main() -> None:
    """Run all tests and report results."""
    
    test_suites = [
        ("tests/test_crypto.py", "Cryptographic Primitives", 7),
        ("tests/test_integrity.py", "Integrity Middleware", 6),
        ("tests/test_llm_integration.py", "LLM Integration", 20),
        ("tests/test_kzg.py", "KZG Commitments", 23),
        ("tests/test_counter_persistence.py", "Counter Persistence", 13),
        ("tests/test_langfuse.py", "Langfuse Integration", 32),
        ("tests/test_otel_spans.py", "OTel Spans", 21),
        ("tests/test_latency_benchmarks.py", "Latency Benchmarking", 16),
        ("tests/test_verify_cli.py", "Verification CLI", 16),
    ]
    
    total_passed = 0
    total_failed = 0
    failed_suites = []
    
    for test_file, description, count in test_suites:
        success, _ = run_pytest(test_file, description, count)
        
        if success:
            total_passed += count
        else:
            total_failed += count
            failed_suites.append((test_file, description))
    
    # Print results
    print(f"\n{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}TEST RESULTS{RESET}")
    print(f"{BOLD}{'='*60}{RESET}\n")
    
    print(f"Total Tests: 158")
    print(f"{GREEN}Passed: {total_passed}{RESET}")
    if total_failed > 0:
        print(f"{RED}Failed: {total_failed}{RESET}")
    
    if failed_suites:
        print(f"\n{RED}Failed Suites:{RESET}")
        for test_file, description in failed_suites:
            print(f"  • {description} ({test_file})")
        return 1
    else:
        print(f"\n{GREEN}[OK] ALL TESTS PASSED{RESET}\n")
        return 0


if __name__ == "__main__":
    sys.exit(main())
