"""Auth middleware — extracts chat_id from Telegram initData bearer token."""
from __future__ import annotations

import json
import logging
import urllib.parse

from flask import request, jsonify

import config

logger = logging.getLogger(__name__)


def get_chat_id_from_request() -> int | None:
    """Extract chat_id from the Authorization header.

    Dev mode:  token starts with "testik_pestik" → config.TELEGRAM_CHAT_ID
    Prod mode: token is URL-encoded Telegram WebApp initData → parse user.id
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None

    token = auth[7:]  # strip "Bearer "
    if not token:
        return None

    # Dev fallback
    if token.startswith("testik_pestik"):
        return config.TELEGRAM_CHAT_ID

    # Production: parse Telegram initData query string
    # Format: "query_id=...&user={"id":123456,...}&auth_date=...&hash=..."
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
