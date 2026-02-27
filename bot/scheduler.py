"""APScheduler — scheduled messages to Telegram for all users."""
from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import Bot

import config
from bot.assistant import morning_briefing, evening_summary
from database.db import get_all_users

logger = logging.getLogger(__name__)


def _send_telegram(chat_id: int, text: str) -> None:
    """Send a plain-text message to a specific Telegram chat."""
    async def _send():
        bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
        await bot.send_message(chat_id=chat_id, text=text)
    asyncio.run(_send())


def _job_morning_briefing() -> None:
    logger.info("[Scheduler] Generating morning briefings…")
    for chat_id in get_all_users():
        try:
            _send_telegram(chat_id, morning_briefing(chat_id))
            logger.info("[Scheduler] Morning briefing sent to %s", chat_id)
        except Exception:
            logger.exception("[Scheduler] Failed morning briefing for %s", chat_id)


def _job_evening_reminder() -> None:
    logger.info("[Scheduler] Sending magnesium reminders…")
    for chat_id in get_all_users():
        try:
            _send_telegram(chat_id, "💊 Не забудь выпить магний!")
        except Exception:
            logger.exception("[Scheduler] Failed reminder for %s", chat_id)


def _job_evening_summary() -> None:
    logger.info("[Scheduler] Generating evening summaries…")
    for chat_id in get_all_users():
        try:
            _send_telegram(chat_id, evening_summary(chat_id))
            logger.info("[Scheduler] Evening summary sent to %s", chat_id)
        except Exception:
            logger.exception("[Scheduler] Failed evening summary for %s", chat_id)


def start_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="UTC")

    scheduler.add_job(
        _job_morning_briefing,
        trigger=CronTrigger(hour=config.MORNING_SUMMARY_HOUR, minute=config.MORNING_SUMMARY_MINUTE),
        id="morning_briefing",
        replace_existing=True,
    )

    scheduler.add_job(
        _job_evening_reminder,
        trigger=CronTrigger(hour=config.EVENING_REMINDER_HOUR, minute=config.EVENING_REMINDER_MINUTE),
        id="evening_reminder",
        replace_existing=True,
    )

    scheduler.add_job(
        _job_evening_summary,
        trigger=CronTrigger(hour=config.EVENING_SUMMARY_HOUR, minute=config.EVENING_SUMMARY_MINUTE),
        id="evening_summary",
        replace_existing=True,
    )

    scheduler.start()
    logger.info(
        "[Scheduler] Started — morning %02d:%02d, reminder %02d:%02d, evening %02d:%02d (UTC)",
        config.MORNING_SUMMARY_HOUR, config.MORNING_SUMMARY_MINUTE,
        config.EVENING_REMINDER_HOUR, config.EVENING_REMINDER_MINUTE,
        config.EVENING_SUMMARY_HOUR, config.EVENING_SUMMARY_MINUTE,
    )
    return scheduler
