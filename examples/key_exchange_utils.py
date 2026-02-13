
import socket
import os
import struct
import json
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

PORT = 5555

def generate_ecdh_keypair():
    """Generate ephemeral ECDH keypair (SECP256R1)"""
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()
    return private_key, public_key

def serialize_public_key(public_key):
    return public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )

def load_public_key(pem_bytes):
    return serialization.load_pem_public_key(pem_bytes)

def derive_shared_key(private_key, peer_public_key):
    """Derive AES-256 key from ECDH shared secret"""
    shared_secret = private_key.exchange(ec.ECDH(), peer_public_key)
    # HKDF to derive strong symmetric key
    key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b'handshake',
    ).derive(shared_secret)
    return key

def encrypt_data(key, plaintext):
    """AES-GCM Encrypt"""
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    return nonce + ciphertext

def decrypt_data(key, data):
    """AES-GCM Decrypt"""
    aesgcm = AESGCM(key)
    nonce = data[:12]
    ciphertext = data[12:]
    return aesgcm.decrypt(nonce, ciphertext, None)

def send_msg(sock, data: bytes):
    """Send length-prefixed message"""
    sock.sendall(struct.pack('!I', len(data)) + data)

def recv_msg(sock) -> bytes:
    """Receive length-prefixed message"""
    raw_len = sock.recv(4)
    if not raw_len: return None
    msg_len = struct.unpack('!I', raw_len)[0]
    data = b''
    while len(data) < msg_len:
        packet = sock.recv(msg_len - len(data))
        if not packet: return None
        data += packet
    return data
