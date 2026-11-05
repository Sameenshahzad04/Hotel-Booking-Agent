#!util/security_util.py
import hashlib
import secrets
import random

UNAMBIGUOUS_CHARS = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"

def generate_session_token() -> str:
    """Generates a secure cryptographic raw session token for user browsers."""
    return secrets.token_urlsafe(32)

def hash_session_token(token: str) -> str:
    """Hashes the session token with SHA-256 for secure storage."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def generate_booking_ref() -> str:
    """Generates human-readable booking reference e.g., BK-982341."""
    return f"BK-{secrets.randbelow(900000) + 100000}"

def generate_confirmation_code() -> str:
    """Generates unambiguous 6-character PC confirmation code: HB-XXXXXX."""
    code = "".join(random.choices(UNAMBIGUOUS_CHARS, k=6))
    return f"HB-{code}"