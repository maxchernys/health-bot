"""Entry point — initializes DB and starts the bot + scheduler."""
import asyncio
import os
import threading
import logging

from flask_cors import CORS

import config
from database.db import init_db
from auth.flask_server import create_flask_app
from api.routes import health_api
from bot.bot import run_bot

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

    # 2. Start Flask server (OAuth callbacks + REST API) in background thread
    flask_app = create_flask_app()
    flask_app.register_blueprint(health_api)
    CORS(flask_app, origins=config.CORS_ORIGINS)
    flask_thread = threading.Thread(target=run_flask, args=(flask_app,), daemon=True)
    flask_thread.start()
    logger.info("OAuth callback server started on :%s", os.getenv("PORT", 8080))

    # 3. Run Telegram bot (blocking)
    logger.info("Starting Telegram bot…")
    await run_bot()


if __name__ == "__main__":
    asyncio.run(main())
