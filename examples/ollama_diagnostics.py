#!/usr/bin/env python3
"""
Ollama Diagnostics Script

Checks Ollama setup and provides guidance for fixing common issues.

Usage:
    PYTHONPATH="." python examples/ollama_diagnostics.py
"""

import sys
import json
from typing import Any

try:
    import requests
except ImportError:
    print("[ERROR] requests library not found. Install with: pip install requests")
    sys.exit(1)

import structlog

logger = structlog.get_logger(__name__)


def print_header(text: str) -> None:
    """Print a formatted header."""
    print(f"\n{'=' * 80}")
    print(f"  {text}")
    print(f"{'=' * 80}\n")


def print_check(label: str, passed: bool, details: str = "") -> None:
    """Print a formatted check result."""
    status = "[OK]" if passed else "[FAIL]"
    print(f"{status} {label}")
    if details:
        print(f"    → {details}")


def check_ollama_connection(base_url: str = "http://localhost:11434") -> bool:
    """Check if Ollama is running and accessible."""
    print_header("1. Ollama Connection")
    
    try:
        response = requests.get(f"{base_url}/api/tags", timeout=5)
        print_check("Ollama Server", True, f"Responding at {base_url}")
        return True
    except requests.exceptions.ConnectionError:
        print_check("Ollama Server", False, f"Cannot connect to {base_url}")
        print("\n  Fix this with:")
        print("    1. Install Ollama from https://ollama.ai")
        print("    2. Run: ollama serve")
        return False
    except requests.exceptions.Timeout:
        print_check("Ollama Server", False, "Connection timeout")
        return False
    except Exception as e:
        print_check("Ollama Server", False, str(e))
        return False


def check_models_available(base_url: str = "http://localhost:11434") -> bool:
    """Check if any models are available."""
    print_header("2. Available Models")
    
    try:
        response = requests.get(f"{base_url}/api/tags", timeout=5)
        data = response.json()
        models = data.get("models", [])
        
        if not models:
            print_check("Models Available", False, "No models found")
            print("\n  Pull a model with one of:")
            print("    ollama pull llama2                    # ~3.8GB")
            print("    ollama pull mistral                   # ~4.1GB")
            print("    ollama pull neural-chat               # ~4.1GB")
            print("    ollama pull openchat                  # ~3.9GB")
            return False
        else:
            print_check("Models Available", True, f"Found {len(models)} model(s)")
            for model in models:
                name = model.get("name", "unknown")
                size = model.get("size", 0)
                size_gb = size / (1024**3)
                print(f"    - {name} ({size_gb:.2f} GB)")
            return True
    except Exception as e:
        print_check("Models Available", False, str(e))
        return False


def test_generate_endpoint(base_url: str = "http://localhost:11434") -> bool:
    """Test the /api/generate endpoint."""
    print_header("3. Generate Endpoint Test")
    
    try:
        # Get available models first
        response = requests.get(f"{base_url}/api/tags", timeout=5)
        models = response.json().get("models", [])
        
        if not models:
            print_check("Generate Endpoint", False, "No models to test with")
            return False
        
        model_name = models[0].get("name", "").split(":")[0]  # Get name without tag
        
        # Test with a simple prompt
        print(f"  Testing with model: {model_name}")
        
        response = requests.post(
            f"{base_url}/api/generate",
            json={
                "model": model_name,
                "prompt": "What is 2+2?",
                "stream": False
            },
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json().get("response", "")
            print_check("Generate Endpoint", True, "Successfully generated response")
            print(f"    Response: {result[:100]}...")
            return True
        else:
            error = response.json().get("error", response.text[:100]) if response.text else str(response.status_code)
            print_check("Generate Endpoint", False, error)
            return False
    except requests.exceptions.Timeout:
        print_check("Generate Endpoint", False, "Request timeout (model taking too long to respond)")
        return False
    except Exception as e:
        print_check("Generate Endpoint", False, str(e))
        return False


def main() -> None:
    """Run all diagnostic checks."""
    print_header("Ollama Configuration Diagnostics")
    
    base_url = "http://localhost:11434"
    
    # Run checks
    connected = check_ollama_connection(base_url)
    if not connected:
        print("\n[ERROR] Cannot proceed without Ollama connection")
        sys.exit(1)
    
    has_models = check_models_available(base_url)
    if not has_models:
        print("\n[INFO] Pull a model and try again")
        sys.exit(1)
    
    test_ok = test_generate_endpoint(base_url)
    
    # Summary
    print_header("Summary")
    if connected and has_models and test_ok:
        print("[SUCCESS] Ollama is properly configured and ready!")
        print("\nYou can now run the validation with:")
        print("  PYTHONPATH=\".\" python examples/validate_phase2.py")
    else:
        print("[WARNING] Some checks failed. Review the output above for fixes.")
        sys.exit(1)


if __name__ == "__main__":
    main()
