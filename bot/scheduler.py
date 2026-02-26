"""APScheduler — morning health briefing sent to Telegram."""
from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import Bot

import config
from bot.assistant import morning_briefing

logger = logging.getLogger(__name__)


def _send_morning_summary() -> None:
    """Blocking function called by APScheduler. Runs async code in a new event loop."""
    logger.info("[Scheduler] Generating morning briefing…")
    try:
        text = morning_briefing()

        async def _send():
            bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
            await bot.send_message(
                chat_id=config.TELEGRAM_CHAT_ID,
                text=text,
            )

        asyncio.run(_send())
        logger.info("[Scheduler] Morning briefing sent.")
    except Exception:
        logger.exception("[Scheduler] Failed to send morning briefing")


def start_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        _send_morning_summary,
        trigger=CronTrigger(
            hour=config.MORNING_SUMMARY_HOUR,
            minute=config.MORNING_SUMMARY_MINUTE,
        ),
        id="morning_summary",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        "[Scheduler] Started — morning briefing at %02d:%02d UTC",
        config.MORNING_SUMMARY_HOUR,
        config.MORNING_SUMMARY_MINUTE,
    )
    return scheduler
