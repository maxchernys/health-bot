"""Entry point — initializes DB and starts the bot + scheduler."""
import asyncio
import os
import threading
import logging

from database.db import init_db
from auth.flask_server import create_flask_app
from bot.bot import run_bot
from bot.scheduler import start_scheduler

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def run_flask(app):
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)


async def main():
    # 1. Initialize database
    init_db()

    # 2. Start Flask OAuth callback server in background thread
    flask_app = create_flask_app()
    flask_thread = threading.Thread(target=run_flask, args=(flask_app,), daemon=True)
    flask_thread.start()
    logger.info("OAuth callback server started on :%s", os.getenv("PORT", 8080))

    # 3. Start APScheduler (morning summaries)
    start_scheduler()

    # 4. Run Telegram bot (blocking)
    logger.info("Starting Telegram bot…")
    await run_bot()


if __name__ == "__main__":
    asyncio.run(main())
