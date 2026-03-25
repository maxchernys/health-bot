"""Sign in with Apple — verify identity token, issue JWT for iOS app."""
from __future__ import annotations

import hashlib
import logging
import time

import jwt
import requests

import config
from database.db import ensure_user, db

logger = logging.getLogger(__name__)

# Apple's public keys endpoint
APPLE_KEYS_URL = "https://appleid.apple.com/auth/keys"
_apple_keys_cache: dict | None = None
_apple_keys_fetched_at: float = 0


def _get_apple_public_keys() -> dict:
    """Fetch and cache Apple's JWKS public keys."""
    global _apple_keys_cache, _apple_keys_fetched_at

    # Cache for 1 hour
    if _apple_keys_cache and (time.time() - _apple_keys_fetched_at) < 3600:
        return _apple_keys_cache

    resp = requests.get(APPLE_KEYS_URL, timeout=10)
    resp.raise_for_status()
    _apple_keys_cache = resp.json()
    _apple_keys_fetched_at = time.time()
    return _apple_keys_cache


def verify_apple_token(identity_token: str) -> dict:
    """Verify Apple identity token and return claims.

    Returns dict with 'sub' (Apple user ID), 'email', etc.
    Raises ValueError if token is invalid.
    """
    # Decode header to find the key ID
    try:
        unverified_header = jwt.get_unverified_header(identity_token)
    except jwt.DecodeError as e:
        raise ValueError(f"Invalid token header: {e}")

    kid = unverified_header.get("kid")
    if not kid:
        raise ValueError("Token header missing 'kid'")

    # Find matching Apple public key
    apple_keys = _get_apple_public_keys()
    matching_key = None
    for key in apple_keys.get("keys", []):
        if key["kid"] == kid:
            matching_key = key
            break

    if not matching_key:
        # Invalidate cache and retry once
        global _apple_keys_cache
        _apple_keys_cache = None
        apple_keys = _get_apple_public_keys()
        for key in apple_keys.get("keys", []):
            if key["kid"] == kid:
                matching_key = key
                break

    if not matching_key:
        raise ValueError(f"No matching Apple public key for kid={kid}")

    # Build RSA public key from JWK
    public_key = jwt.algorithms.RSAAlgorithm.from_jwk(matching_key)

    # Verify and decode
    try:
        claims = jwt.decode(
            identity_token,
            key=public_key,
            algorithms=["RS256"],
            audience=config.APPLE_BUNDLE_ID,
            issuer="https://appleid.apple.com",
        )
    except jwt.ExpiredSignatureError:
        raise ValueError("Apple token expired")
    except jwt.InvalidTokenError as e:
        raise ValueError(f"Invalid Apple token: {e}")

    return claims


def apple_user_to_chat_id(apple_user_id: str) -> int:
    """Convert Apple user ID (string) to a numeric chat_id.

    Uses a stable hash to create a unique integer that won't collide
    with Telegram chat_ids (which are typically < 10 billion).
    Apple IDs are hashed to the range 10_000_000_000 — 19_999_999_999.
    """
    hash_int = int(hashlib.sha256(apple_user_id.encode()).hexdigest()[:15], 16)
    return 10_000_000_000 + (hash_int % 10_000_000_000)


def issue_jwt(chat_id: int, apple_user_id: str, email: str | None = None) -> str:
    """Issue a JWT token for the iOS app."""
    payload = {
        "chat_id": chat_id,
        "apple_sub": apple_user_id,
        "email": email,
        "iat": int(time.time()),
        "exp": int(time.time()) + 90 * 24 * 3600,  # 90 days
    }
    return jwt.encode(payload, config.JWT_SECRET, algorithm="HS256")


def decode_jwt(token: str) -> dict | None:
    """Decode and verify a JWT token. Returns payload or None."""
    try:
        return jwt.decode(token, config.JWT_SECRET, algorithms=["HS256"])
    except jwt.InvalidTokenError:
        return None


def handle_apple_signin(identity_token: str) -> dict:
    """Full Sign in with Apple flow:
    1. Verify Apple identity token
    2. Create/find user
    3. Issue JWT

    Returns {"token": "...", "chat_id": ..., "email": ...}
    """
    claims = verify_apple_token(identity_token)

    apple_user_id = claims["sub"]
    email = claims.get("email")
    chat_id = apple_user_to_chat_id(apple_user_id)

    # Register user
    ensure_user(chat_id)

    # Save Apple user mapping
    with db() as conn:
        conn.execute(
            """INSERT INTO apple_users (apple_user_id, chat_id, email)
               VALUES (?, ?, ?)
               ON CONFLICT(apple_user_id) DO UPDATE SET email = excluded.email""",
            (apple_user_id, chat_id, email),
        )

    token = issue_jwt(chat_id, apple_user_id, email)

    logger.info("[Apple Auth] User signed in: chat_id=%d, email=%s", chat_id, email)

    return {
        "token": token,
        "chat_id": chat_id,
        "email": email,
    }
