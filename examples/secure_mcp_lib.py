
import os
import json
import socket
import struct
import examples.key_exchange_utils as kex
from src.crypto.encoding import canonicalize_json

def secure_listen_and_serve(tool_name: str, handler_func, port=5555):
    """
    Starts a generic secure tool server.
    1. Performs ECDH Handshake
    2. Receives Provisioning Key
    3. Loops: Receive Request -> Process -> Sign -> Send Response
    """
    from src.security.key_management import ToolSigner
    from src.crypto.encoding import canonicalize_json

    print(f"=== REMOTE TOOL '{tool_name}' (Secure MCP Worker) ===")
    print(f"Listening on port {port}...")
    
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.bind(('0.0.0.0', port))
    server_sock.listen(1)
    
    conn, addr = server_sock.accept()
    print(f"\n[Net] Connection from {addr}")
    
    try:
        # --- ECDH HANDSHAKE ---
        priv_key, pub_key = kex.generate_ecdh_keypair()
        kex.send_msg(conn, kex.serialize_public_key(pub_key))
        peer_pub = kex.load_public_key(kex.recv_msg(conn))
        shared_key = kex.derive_shared_key(priv_key, peer_pub)
        print("[KEX] Secure Channel Established")
        
        # --- PROVISIONING ---
        encrypted_ibs_key = kex.recv_msg(conn)
        ibs_key_str = kex.decrypt_data(shared_key, encrypted_ibs_key).decode('utf-8')
        signer = ToolSigner.import_from_string(tool_name, ibs_key_str)
        print(f"[Identity] Key provisioned for '{tool_name}'")
        
        # --- REQUEST LOOP ---
        while True:
            encrypted_req = kex.recv_msg(conn)
            if not encrypted_req: break
            
            req_str = kex.decrypt_data(shared_key, encrypted_req).decode('utf-8')
            envelope = json.loads(req_str)
            
            request_id = envelope.get("request_id")
            args = envelope.get("args", {})
            
            print(f"Processing Request: {request_id}")
            
            # Execute Logic
            try:
                result = handler_func(args)
            except Exception as e:
                result = {"error": str(e)}

            # --- SIGNING WITH CONTEXT BINDING ---
            # We sign (Result + Request ID) to prevent Replay Attacks
            # This binds the answer "42" to the specific question ID "req_123"
            payload = {
                "tool": tool_name, 
                "result": result,
                "request_id": request_id
            }
            
            payload_bytes = canonicalize_json(payload).encode("utf-8")
            signature = signer.sign_message(payload_bytes)
            
            response_bundle = {
                "tool": tool_name,
                "result": result,
                "request_id": request_id,
                "signature": str(signature)
            }
            
            # Encrypt Response
            resp_bytes = json.dumps(response_bundle).encode('utf-8')
            kex.send_msg(conn, kex.encrypt_data(shared_key, resp_bytes))
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()
        server_sock.close()


class SecureMCPClient:
    """
    Client-side helper for the Agent to connect to Secure Tools.
    Handles KEX, Provisioning, and Request/Response verification.
    """
    def __init__(self, tool_name, host='localhost', port=5555, middleware=None):
        self.tool_name = tool_name
        self.addr = (host, port)
        self.middleware = middleware
        self.sock = None
        self.shared_key = None
        
    def connect_and_provision(self):
        """Connects and provisions the remote tool with a derived key"""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect(self.addr)
        
        # KEX
        priv, pub = kex.generate_ecdh_keypair()
        peer_pub = kex.load_public_key(kex.recv_msg(self.sock))
        kex.send_msg(self.sock, kex.serialize_public_key(pub))
        self.shared_key = kex.derive_shared_key(priv, peer_pub)
        
        # Provision
        signer = self.middleware._get_signer(self.tool_name)
        key_str = signer.export_private_key()
        kex.send_msg(self.sock, kex.encrypt_data(self.shared_key, key_str.encode('utf-8')))
        
    def call_tool(self, args: dict, request_id: str) -> dict:
        """Sends request and verifies the signature of the response"""
        envelope = {"args": args, "request_id": request_id}
        req_bytes = json.dumps(envelope).encode('utf-8')
        kex.send_msg(self.sock, kex.encrypt_data(self.shared_key, req_bytes))
        
        # Receive
        enc_resp = kex.recv_msg(self.sock)
        resp_str = kex.decrypt_data(self.shared_key, enc_resp).decode('utf-8')
        resp = json.loads(resp_str)
        
        # Verify
        self._verify_response(resp, request_id)
        return resp
        
    def _verify_response(self, resp, expected_req_id):
        """Verify signature binding: (Result + RequestID + ToolID)"""
        from src.security.key_management import Verifier
        from src.crypto.encoding import canonicalize_json
        import ast
        from py_ecc.optimized_bls12_381 import FQ

        if resp["request_id"] != expected_req_id:
            raise ValueError("Replay Attack Detected: Request ID mismatch")
            
        verifier = Verifier(self.middleware.authority.mpk)
        
        # Reconstruct exactly what the tool signed
        payload_check = {
            "tool": self.tool_name, 
            "result": resp["result"],
            "request_id": resp["request_id"]
        }
        msg_bytes = canonicalize_json(payload_check).encode("utf-8")
        
        # Parse Sig
        sig_tuple = ast.literal_eval(resp["signature"])
        def parse_g1(t): return (FQ(t[0]), FQ(t[1]), FQ(t[2]))
        sig_g1_pair = (parse_g1(sig_tuple[0]), parse_g1(sig_tuple[1]))
        
        if not verifier.verify_tool_signature(self.tool_name, msg_bytes, sig_g1_pair):
            raise ValueError("Invalid Signature: Forgery detected")
            
    def close(self):
        if self.sock: self.sock.close()
