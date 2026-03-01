"""Telegram bot — handlers for commands and health assistant messages."""
from __future__ import annotations

import asyncio
import logging

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from telegram.constants import ParseMode

import config
from auth.flask_server import get_auth_url, get_valid_token
from aggregator.aggregator import aggregate
from bot.assistant import ask_health_assistant
from database.db import ensure_user
from utils.formatting import format_health_summary

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    ensure_user(chat_id)
    text = (
        "👋 *Health Bot*\n\n"
        "Commands:\n"
        "  /health — full health summary\n"
        "  /calories — калории за сегодня\n"
        "  /connect\\_whoop — authorize Whoop\n"
        "  /connect\\_oura — authorize Oura\n"
        "  /status — connection status\n\n"
        "💬 Просто напиши вопрос — я проанализирую твои данные Whoop и Oura."
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def cmd_health(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    ensure_user(chat_id)
    msg = await update.message.reply_text("⏳ Fetching health data…")
    try:
        data = aggregate(chat_id)
        text = format_health_summary(data)
        await msg.edit_text(text, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.exception("[Bot] /health error")
        await msg.edit_text(f"❌ Error: {e}")


async def cmd_connect_whoop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    ensure_user(chat_id)
    url = get_auth_url(chat_id, "whoop")
    await update.message.reply_text(
        f"🔗 [Connect Whoop]({url})\n\nOpen the link, authorize, then come back.",
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True,
    )


async def cmd_connect_oura(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    ensure_user(chat_id)
    url = get_auth_url(chat_id, "oura")
    await update.message.reply_text(
        f"🔗 [Connect Oura Ring]({url})\n\nOpen the link, authorize, then come back.",
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True,
    )


async def cmd_calories(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    ensure_user(chat_id)
    msg = await update.message.reply_text("⏳ Считаю калории…")
    try:
        data = aggregate(chat_id)
        w = data.get("whoop", {})
        o = data.get("oura", {})
        lines = [f"🔥 *Калории за сегодня*\n"]

        # Whoop
        w_cal = w.get("day_calories_kcal")
        w_workout_cal = w.get("workout_calories_kcal")
        lines.append("*Whoop*")
        lines.append(f"  За день:    `{w_cal:.0f} kcal`" if w_cal else "  За день:    —")
        lines.append(f"  Тренировка: `{w_workout_cal:.0f} kcal`" if w_workout_cal else "  Тренировка: —")

        # Oura
        o_total = o.get("total_calories")
        o_active = o.get("active_calories")
        lines.append("\n*Oura*")
        if o_total:
            bmr = o_total - (o_active or 0)
            lines.append(f"  За день:    `{o_total:,} kcal`")
            lines.append(f"  Активные:   `{o_active or 0:,} kcal`")
            lines.append(f"  BMR:        `{bmr:,} kcal`")
        else:
            lines.append("  За день:    —")

        await msg.edit_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.exception("[Bot] /calories error")
        await msg.edit_text(f"❌ Error: {e}")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    ensure_user(chat_id)
    whoop_ok = get_valid_token(chat_id, "whoop") is not None
    oura_ok = get_valid_token(chat_id, "oura") is not None
    whoop_str = "✅ connected" if whoop_ok else "❌ not connected — /connect\\_whoop"
    oura_str = "✅ connected" if oura_ok else "❌ not connected — /connect\\_oura"
    lines = [
        "🔌 *Connection Status*",
        f"  Whoop: {whoop_str}",
        f"  Oura:  {oura_str}",
    ]
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


# ---------------------------------------------------------------------------
# Text message handler — health assistant
# ---------------------------------------------------------------------------

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    ensure_user(chat_id)
    question = update.message.text
    msg = await update.message.reply_text("🤔 Анализирую…")
    try:
        answer = ask_health_assistant(chat_id, question)
        await msg.edit_text(answer)
    except Exception as e:
        logger.exception("[Bot] handle_message error")
        await msg.edit_text(f"❌ Ошибка: {e}")


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def build_application() -> Application:
    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("health", cmd_health))
    app.add_handler(CommandHandler("connect_whoop", cmd_connect_whoop))
    app.add_handler(CommandHandler("connect_oura", cmd_connect_oura))
    app.add_handler(CommandHandler("calories", cmd_calories))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    return app


async def run_bot() -> None:
    """Start the bot with polling (blocking)."""
    application = build_application()
    await application.initialize()
    await application.start()
    await application.updater.start_polling(drop_pending_updates=True)
    logger.info("[Bot] Polling started")
    stop_event = asyncio.Event()
    try:
        await stop_event.wait()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        await application.updater.stop()
        await application.stop()
        await application.shutdown()
