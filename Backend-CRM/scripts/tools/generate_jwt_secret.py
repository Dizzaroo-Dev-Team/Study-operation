"""
Generate secure JWT secret for ONLYOFFICE Document Server.

Run this script to generate a secure 32-byte random secret:
    python generate_jwt_secret.py

Add the output to your .env file:
    ONLYOFFICE_JWT_SECRET=<generated_secret>
"""

import secrets

if __name__ == "__main__":
    secret = secrets.token_hex(32)
    print("=" * 70)
    print("ONLYOFFICE JWT Secret Generator")
    print("=" * 70)
    print()
    print("Generated secret (64 hex characters):")
    print(secret)
    print()
    print("Add this to your .env file:")
    print(f"ONLYOFFICE_JWT_SECRET={secret}")
    print()
    print("=" * 70)
