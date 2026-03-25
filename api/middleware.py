"""Auth middleware — extracts chat_id from bearer token.

Supports three token types:
1. Dev token:  starts with "testik_pestik" → config.TELEGRAM_CHAT_ID
2. JWT token:  issued by /api/auth/apple → decode to get chat_id
3. Telegram initData:  URL-encoded query string → parse user.id
"""
from __future__ import annotations

import json
import logging
import urllib.parse

from flask import request, jsonify

import config

logger = logging.getLogger(__name__)


def get_chat_id_from_request() -> int | None:
    """Extract chat_id from the Authorization header."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None

    token = auth[7:]  # strip "Bearer "
    if not token:
        return None

    # 1. Dev fallback
    if token.startswith("testik_pestik"):
        return config.TELEGRAM_CHAT_ID

    # 2. JWT token (from iOS Sign in with Apple)
    if token.count(".") == 2:  # JWT has 3 parts separated by dots
        try:
            from auth.apple_auth import decode_jwt
            payload = decode_jwt(token)
            if payload and "chat_id" in payload:
                return int(payload["chat_id"])
        except Exception as e:
            logger.warning("[Auth] JWT decode failed: %s", e)

    # 3. Telegram initData query string
    try:
        parsed = urllib.parse.parse_qs(token)
        user_json = parsed.get("user", [""])[0]
        if user_json:
            user = json.loads(user_json)
            return int(user["id"])
    except (json.JSONDecodeError, KeyError, ValueError, IndexError) as e:
        logger.warning("[Auth] Failed to parse initData: %s", e)

    return None


def require_auth(f):
    """Decorator that extracts chat_id and returns 401 if missing."""
    from functools import wraps

    @wraps(f)
    def decorated(*args, **kwargs):
        chat_id = get_chat_id_from_request()
        if chat_id is None:
            return jsonify({"error": "Unauthorized"}), 401
        return f(chat_id, *args, **kwargs)

    return decorated
