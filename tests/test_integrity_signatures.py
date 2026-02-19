"""
Test integration of IBS Signatures into Integrity Middleware
"""

import json
from src.integrity import IntegrityMiddleware
from src.config import get_settings

def test_integrity_chain_signatures():
    # 1. Init Middleware (generates ephemeral key)
    middleware = IntegrityMiddleware()
    # Ensure ephemeral
    get_settings().security.master_secret_key = None 
    
    # 2. Record Events
    print("Recording events...")
    middleware.record_prompt("Hello Agent")
    middleware.record_tool_input("calculator", {"a": 1, "b": 2})
    middleware.record_tool_output("calculator", 3)
    middleware.record_model_output("The result is 3")
    
    # 3. Finalize
    result = middleware.finalize()
    
    # 4. Verification Check
    print("\n--- Final Proof ---")
    print(json.dumps(result, indent=2))
    
    assert "root_signature" in result
    assert "server_mpk" in result
    
    # 5. Check events inside accumulator for signatures
    print("\n--- Event Log ---")
    events = middleware.verkle_accumulator.events
    for ev in events:
        assert "signature" in ev, f"Event {ev['counter']} missing signature"
        assert "signer_id" in ev, f"Event {ev['counter']} missing signer_id"
        print(f"Event {ev['counter']} ({ev['event_type']}): Signed by '{ev['signer_id']}'")
        
        if ev['event_type'] == 'tool_output':
            assert ev['signer_id'] == 'calculator'
        else:
            assert ev['signer_id'] == 'server'

if __name__ == "__main__":
    test_integrity_chain_signatures()
