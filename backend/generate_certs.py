#!/usr/bin/env python3
"""
Generate self-signed SSL certificates for local HTTPS development.

This script creates:
- localhost.key (private key)
- localhost.crt (self-signed certificate)

Run this once before starting the server with HTTPS.
The certificates are valid for 365 days.

Usage:
    python backend/generate_certs.py

The generated files will be placed in the 'certs/' directory in the project root.
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timedelta

try:
    from cryptography import x509
    from cryptography.x509.oid import NameOID, ExtensionOID
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
except ImportError:
    print("Error: 'cryptography' library is required.")
    print("Install it with: pip install cryptography")
    sys.exit(1)


def generate_self_signed_cert(cert_path: Path, key_path: Path, hostname: str = "localhost"):
    """
    Generate a self-signed certificate and private key.
    
    Args:
        cert_path: Path to save the certificate (.crt file)
        key_path: Path to save the private key (.key file)
        hostname: Hostname for the certificate (default: localhost)
    """
    # Generate private key
    print("Generating private key...")
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )
    
    # Build certificate
    print("Building self-signed certificate...")
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, u"US"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, u"Development"),
        x509.NameAttribute(NameOID.LOCALITY_NAME, u"Local"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, u"Development"),
        x509.NameAttribute(NameOID.COMMON_NAME, hostname),
    ])
    
    cert = x509.CertificateBuilder().subject_name(
        subject
    ).issuer_name(
        issuer
    ).public_key(
        private_key.public_key()
    ).serial_number(
        x509.random_serial_number()
    ).not_valid_before(
        datetime.utcnow()
    ).not_valid_after(
        datetime.utcnow() + timedelta(days=365)
    ).add_extension(
        x509.SubjectAlternativeName([
            x509.DNSName(hostname),
            x509.DNSName("*.localhost"),
            x509.DNSName("127.0.0.1"),
        ]),
        critical=False,
    ).sign(private_key, hashes.SHA256(), default_backend())
    
    # Write private key
    print(f"Writing private key to {key_path}...")
    with open(key_path, "wb") as f:
        f.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        ))
    os.chmod(key_path, 0o600)  # Restrict permissions
    
    # Write certificate
    print(f"Writing certificate to {cert_path}...")
    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    
    print(f"\n✓ Certificates generated successfully!")
    print(f"  Certificate: {cert_path}")
    print(f"  Private key: {key_path}")
    print(f"\nThe HMAC key will now be transmitted over HTTPS (encrypted).")
    print(f"Note: Browsers will show a warning for self-signed certs on first visit.")
    print(f"      This is expected for local development — just accept the warning.")


def main():
    # Create certs directory in project root
    project_root = Path(__file__).parent.parent
    certs_dir = project_root / "certs"
    certs_dir.mkdir(exist_ok=True)
    
    cert_path = certs_dir / "localhost.crt"
    key_path = certs_dir / "localhost.key"
    
    # Check if certs already exist
    if cert_path.exists() and key_path.exists():
        print(f"Certificates already exist:")
        print(f"  Certificate: {cert_path}")
        print(f"  Private key: {key_path}")
        response = input("\nOverwrite? (y/N): ").strip().lower()
        if response != "y":
            print("Aborting.")
            return
    
    try:
        generate_self_signed_cert(cert_path, key_path)
        
        # Print next steps
        print(f"\n--- Next Steps ---")
        print(f"1. Start the server with HTTPS:")
        print(f"   python backend/server.py --https")
        print(f"\n2. Or set environment variable:")
        print(f"   $env:USE_HTTPS='true'; python backend/server.py")
        print(f"\n3. Visit: https://localhost:8000 (accept certificate warning)")
        
    except Exception as e:
        print(f"Error generating certificates: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
