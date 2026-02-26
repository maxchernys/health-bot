"""APScheduler — scheduled messages to Telegram."""
from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import Bot

import config
from bot.assistant import morning_briefing, evening_summary

logger = logging.getLogger(__name__)


def _send_telegram(text: str) -> None:
    """Send a plain-text message to the configured Telegram chat."""
    async def _send():
        bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
        await bot.send_message(chat_id=config.TELEGRAM_CHAT_ID, text=text)
    asyncio.run(_send())


def _job_morning_briefing() -> None:
    logger.info("[Scheduler] Generating morning briefing…")
    try:
        _send_telegram(morning_briefing())
        logger.info("[Scheduler] Morning briefing sent.")
    except Exception:
        logger.exception("[Scheduler] Failed to send morning briefing")


def _job_evening_reminder() -> None:
    logger.info("[Scheduler] Sending magnesium reminder…")
    try:
        _send_telegram("💊 Не забудь выпить магний!")
        logger.info("[Scheduler] Magnesium reminder sent.")
    except Exception:
        logger.exception("[Scheduler] Failed to send magnesium reminder")


def _job_evening_summary() -> None:
    logger.info("[Scheduler] Generating evening summary…")
    try:
        _send_telegram(evening_summary())
        logger.info("[Scheduler] Evening summary sent.")
    except Exception:
        logger.exception("[Scheduler] Failed to send evening summary")


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
