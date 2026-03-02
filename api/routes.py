"""REST API Blueprint for MealCheck frontend — health endpoints."""
from __future__ import annotations

import logging

from flask import Blueprint, request, jsonify

from api.middleware import require_auth
from auth.flask_server import get_auth_url
from aggregator.aggregator import aggregate
from bot.assistant import ask_health_assistant
from database.db import (
    ensure_user,
    get_connection_status,
    delete_oauth_token,
    get_health_history,
    get_recent_messages,
)

logger = logging.getLogger(__name__)

health_api = Blueprint("health_api", __name__, url_prefix="/api/health")


@health_api.route("/connections", methods=["GET"])
@require_auth
def connections(chat_id: int):
    """Return device connection status."""
    return jsonify(get_connection_status(chat_id))


@health_api.route("/connect/<provider>", methods=["GET"])
@require_auth
def connect_device(chat_id: int, provider: str):
    """Generate OAuth authorization URL for a provider."""
    if provider not in ("whoop", "oura"):
        return jsonify({"error": f"Unknown provider: {provider}"}), 400

    try:
        ensure_user(chat_id)
        auth_url = get_auth_url(chat_id, provider)
        return jsonify({"auth_url": auth_url})
    except Exception as e:
        logger.exception("[API] Failed to generate auth URL for %s", provider)
        return jsonify({"error": str(e)}), 500


@health_api.route("/connect/<provider>", methods=["DELETE"])
@require_auth
def disconnect_device(chat_id: int, provider: str):
    """Remove OAuth token for a provider."""
    if provider not in ("whoop", "oura"):
        return jsonify({"error": f"Unknown provider: {provider}"}), 400

    delete_oauth_token(chat_id, provider)
    return "", 200


@health_api.route("/summary", methods=["GET"])
@require_auth
def summary(chat_id: int):
    """Return current health summary from WHOOP + Oura."""
    try:
        data = aggregate(chat_id)
        # Strip internal keys (prefixed with _) from whoop/oura dicts
        whoop = {k: v for k, v in data.get("whoop", {}).items() if not k.startswith("_")} or None
        oura = {k: v for k, v in data.get("oura", {}).items() if not k.startswith("_")} or None

        return jsonify({
            "date": data["date"],
            "composite_recovery": data["composite_recovery"],
            "training_readiness": data["training_readiness"],
            "whoop": whoop,
            "oura": oura,
            "errors": data["errors"],
        })
    except Exception as e:
        logger.exception("[API] Summary failed")
        return jsonify({"error": str(e)}), 500


@health_api.route("/history", methods=["GET"])
@require_auth
def history(chat_id: int):
    """Return health history for the last N days."""
    days = request.args.get("days", 7, type=int)
    days = max(1, min(days, 90))
    return jsonify(get_health_history(chat_id, days))


@health_api.route("/trends", methods=["GET"])
@require_auth
def trends(chat_id: int):
    """Return health trends — same format as /history."""
    days = request.args.get("days", 7, type=int)
    days = max(1, min(days, 90))
    return jsonify(get_health_history(chat_id, days))


@health_api.route("/chat/history", methods=["GET"])
@require_auth
def chat_history(chat_id: int):
    """Return conversation history."""
    limit = request.args.get("limit", 50, type=int)
    limit = max(1, min(limit, 200))
    return jsonify(get_recent_messages(chat_id, limit))


@health_api.route("/chat", methods=["POST"])
@require_auth
def chat(chat_id: int):
    """Send a message to the AI health assistant."""
    body = request.get_json(silent=True) or {}
    message = body.get("message", "").strip()

    if not message:
        return jsonify({"error": "Message is required"}), 400

    try:
        reply = ask_health_assistant(chat_id, message)
        return jsonify({"reply": reply})
    except Exception as e:
        logger.exception("[API] Chat failed")
        return jsonify({"error": str(e)}), 500
