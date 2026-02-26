"""APScheduler — morning health summary sent to Telegram at 08:00."""
from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import Bot
from telegram.constants import ParseMode

import config
from aggregator.aggregator import aggregate
from utils.formatting import format_health_summary

logger = logging.getLogger(__name__)


def _send_morning_summary() -> None:
    """Blocking function called by APScheduler. Runs async code in a new event loop."""
    logger.info("[Scheduler] Sending morning summary…")
    try:
        data = aggregate()
        full_text = format_health_summary(data)

        async def _send():
            bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
            await bot.send_message(
                chat_id=config.TELEGRAM_CHAT_ID,
                text=full_text,
                parse_mode=ParseMode.MARKDOWN,
            )

        asyncio.run(_send())
        logger.info("[Scheduler] Morning summary sent.")
    except Exception:
        logger.exception("[Scheduler] Failed to send morning summary")


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
        "[Scheduler] Started — morning summary at %02d:%02d UTC",
        config.MORNING_SUMMARY_HOUR,
        config.MORNING_SUMMARY_MINUTE,
    )
    return scheduler
