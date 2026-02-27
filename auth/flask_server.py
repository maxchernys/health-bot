"""Flask server handling OAuth2 callbacks for Whoop and Oura."""
from __future__ import annotations

import time
import secrets
import logging
import requests
from flask import Flask, request, redirect

import config
from database.db import db

logger = logging.getLogger(__name__)


def _save_state(state: str, provider: str, chat_id: int) -> None:
    with db() as conn:
        conn.execute(
            "INSERT INTO oauth_states (state, provider, chat_id) VALUES (?, ?, ?)",
            (state, provider, chat_id),
        )


def _pop_state(state: str) -> tuple[str, int] | None:
    """Return (provider, chat_id) for the given state and delete it."""
    with db() as conn:
        row = conn.execute(
            "SELECT provider, chat_id FROM oauth_states WHERE state = ?", (state,)
        ).fetchone()
        if row:
            conn.execute("DELETE FROM oauth_states WHERE state = ?", (state,))
            return row["provider"], row["chat_id"]
    return None


def _save_token(chat_id: int, provider: str, token_data: dict) -> None:
    expires_at = int(time.time()) + token_data.get("expires_in", 3600)
    with db() as conn:
        conn.execute(
            """
            INSERT INTO oauth_tokens (chat_id, provider, access_token, refresh_token, expires_at, updated_at)
            VALUES (?, ?, ?, ?, ?, strftime('%s', 'now'))
            ON CONFLICT(chat_id, provider) DO UPDATE SET
                access_token  = excluded.access_token,
                refresh_token = excluded.refresh_token,
                expires_at    = excluded.expires_at,
                updated_at    = excluded.updated_at
            """,
            (
                chat_id,
                provider,
                token_data["access_token"],
                token_data.get("refresh_token"),
                expires_at,
            ),
        )
    logger.info("[Auth] Token saved for chat_id=%s provider=%s", chat_id, provider)


def get_auth_url(chat_id: int, provider: str) -> str:
    """Return the OAuth2 authorization URL for the given provider."""
    state = secrets.token_urlsafe(16)
    _save_state(state, provider, chat_id)

    if provider == "whoop":
        params = {
            "client_id": config.WHOOP_CLIENT_ID,
            "redirect_uri": config.OAUTH_REDIRECT_URI_WHOOP,
            "response_type": "code",
            "scope": config.WHOOP_SCOPES,
            "state": state,
        }
        base = config.WHOOP_AUTH_URL
    elif provider == "oura":
        params = {
            "client_id": config.OURA_CLIENT_ID,
            "redirect_uri": config.OAUTH_REDIRECT_URI_OURA,
            "response_type": "code",
            "scope": config.OURA_SCOPES,
            "state": state,
        }
        base = config.OURA_AUTH_URL
    else:
        raise ValueError(f"Unknown provider: {provider}")

    from urllib.parse import urlencode
    return f"{base}?{urlencode(params)}"


def _exchange_code(provider: str, code: str) -> dict:
    if provider == "whoop":
        resp = requests.post(
            config.WHOOP_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": config.OAUTH_REDIRECT_URI_WHOOP,
                "client_id": config.WHOOP_CLIENT_ID,
                "client_secret": config.WHOOP_CLIENT_SECRET,
            },
            timeout=15,
        )
    elif provider == "oura":
        resp = requests.post(
            config.OURA_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": config.OAUTH_REDIRECT_URI_OURA,
            },
            auth=(config.OURA_CLIENT_ID, config.OURA_CLIENT_SECRET),
            timeout=15,
        )
    else:
        raise ValueError(f"Unknown provider: {provider}")

    resp.raise_for_status()
    return resp.json()


def refresh_token(chat_id: int, provider: str) -> str | None:
    """Refresh access token for the given user+provider. Returns new access_token or None."""
    with db() as conn:
        row = conn.execute(
            "SELECT refresh_token FROM oauth_tokens WHERE chat_id = ? AND provider = ?",
            (chat_id, provider),
        ).fetchone()

    if not row or not row["refresh_token"]:
        logger.warning("[Auth] No refresh token for chat_id=%s provider=%s", chat_id, provider)
        return None

    try:
        if provider == "whoop":
            resp = requests.post(
                config.WHOOP_TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": row["refresh_token"],
                    "client_id": config.WHOOP_CLIENT_ID,
                    "client_secret": config.WHOOP_CLIENT_SECRET,
                },
                timeout=15,
            )
        elif provider == "oura":
            resp = requests.post(
                config.OURA_TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": row["refresh_token"],
                },
                auth=(config.OURA_CLIENT_ID, config.OURA_CLIENT_SECRET),
                timeout=15,
            )
        else:
            return None

        resp.raise_for_status()
        token_data = resp.json()
        _save_token(chat_id, provider, token_data)
        return token_data["access_token"]
    except Exception as e:
        logger.error("[Auth] Token refresh failed for chat_id=%s %s: %s", chat_id, provider, e)
        return None


def get_valid_token(chat_id: int, provider: str) -> str | None:
    """Return a valid access token, refreshing if needed."""
    with db() as conn:
        row = conn.execute(
            "SELECT access_token, expires_at FROM oauth_tokens WHERE chat_id = ? AND provider = ?",
            (chat_id, provider),
        ).fetchone()

    if not row:
        return None

    # Refresh 60 seconds before expiry
    if row["expires_at"] and int(time.time()) >= row["expires_at"] - 60:
        return refresh_token(chat_id, provider)

    return row["access_token"]


def create_flask_app() -> Flask:
    app = Flask(__name__)

    @app.route("/callback/whoop")
    def whoop_callback():
        state = request.args.get("state", "")
        code = request.args.get("code", "")
        error = request.args.get("error")

        if error:
            logger.error("[Auth] Whoop OAuth error: %s", error)
            return f"<h2>Whoop auth error: {error}</h2>", 400

        result = _pop_state(state)
        if result is None or result[0] != "whoop":
            return "<h2>Invalid state</h2>", 400
        _, chat_id = result

        try:
            token_data = _exchange_code("whoop", code)
            _save_token(chat_id, "whoop", token_data)
            return "<h2>Whoop connected! You can close this tab.</h2>"
        except Exception as e:
            logger.exception("[Auth] Whoop code exchange failed")
            return f"<h2>Error: {e}</h2>", 500

    @app.route("/callback/oura")
    def oura_callback():
        state = request.args.get("state", "")
        code = request.args.get("code", "")
        error = request.args.get("error")

        if error:
            logger.error("[Auth] Oura OAuth error: %s", error)
            return f"<h2>Oura auth error: {error}</h2>", 400

        result = _pop_state(state)
        if result is None or result[0] != "oura":
            return "<h2>Invalid state</h2>", 400
        _, chat_id = result

        try:
            token_data = _exchange_code("oura", code)
            _save_token(chat_id, "oura", token_data)
            return "<h2>Oura connected! You can close this tab.</h2>"
        except Exception as e:
            logger.exception("[Auth] Oura code exchange failed")
            return f"<h2>Error: {e}</h2>", 500

    @app.route("/health")
    def health():
        return {"status": "ok"}, 200

    return app
