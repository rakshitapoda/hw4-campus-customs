"""Password hashing and session tokens (standard library only)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / '.env')

HASH_ALGORITHM = 'pbkdf2_sha256'
# New accounts use OWASP's current recommendation for PBKDF2-HMAC-SHA256.
PBKDF2_ITERATIONS = 600_000
# The accounts already in the database use "pbkdf2_sha256$<salt>$<hex digest>" with no iteration
# count stored; 120,000 iterations was confirmed by verifying the provided test account.
LEGACY_PBKDF2_ITERATIONS = 120_000
SALT_BYTES = 16

SESSION_TTL_SECONDS = 60 * 60 * 24 * 7  # 7 days
# Set AUTH_SECRET_KEY in .env so sessions survive restarts; otherwise a random key is used per process.
SESSION_SECRET = os.environ.get('AUTH_SECRET_KEY') or secrets.token_hex(32)


# ---------- Passwords ----------

def _pbkdf2(password: str, salt: str, iterations: int) -> str:
    return hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), iterations).hex()


def hash_password(password: str) -> str:
    """Return "pbkdf2_sha256$<iterations>$<salt>$<hex digest>" with a fresh random salt."""
    salt = secrets.token_hex(SALT_BYTES)
    digest = _pbkdf2(password, salt, PBKDF2_ITERATIONS)
    return f'{HASH_ALGORITHM}${PBKDF2_ITERATIONS}${salt}${digest}'


def verify_password(password: str, stored_hash: str) -> bool:
    """Check a password against either the new 4-part or the legacy 3-part hash format."""
    parts = stored_hash.split('$')
    if parts[0] != HASH_ALGORITHM:
        return False
    if len(parts) == 4 and parts[1].isdigit():
        _, iterations, salt, digest = parts
        iterations_int = int(iterations)
    elif len(parts) == 3:
        _, salt, digest = parts
        iterations_int = LEGACY_PBKDF2_ITERATIONS
    else:
        return False
    return hmac.compare_digest(_pbkdf2(password, salt, iterations_int), digest)


# Used when an email is unknown so the response takes as long as a real password check.
_DUMMY_HASH = hash_password(secrets.token_hex(16))


def burn_password_check(password: str) -> None:
    verify_password(password, _DUMMY_HASH)


# ---------- Session tokens ----------

def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + '=' * (-len(text) % 4))


def create_session_token(user_id: int) -> str:
    """Signed token "<payload>.<signature>" carrying the user id and an expiry time."""
    payload = _b64(json.dumps({'uid': user_id, 'exp': int(time.time()) + SESSION_TTL_SECONDS}).encode())
    signature = _b64(hmac.new(SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).digest())
    return f'{payload}.{signature}'


def read_session_token(token: str) -> int | None:
    """Return the user id if the token is authentic and unexpired, else None."""
    try:
        payload, signature = token.split('.')
        expected = _b64(hmac.new(SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            return None
        data = json.loads(_unb64(payload))
        if int(data['exp']) < time.time():
            return None
        return int(data['uid'])
    except (ValueError, KeyError, TypeError):
        return None
