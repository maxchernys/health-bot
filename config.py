import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(override=True)

# --- Telegram ---
TELEGRAM_BOT_TOKEN: str = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID: int = int(os.environ["TELEGRAM_CHAT_ID"])

# --- Whoop ---
WHOOP_CLIENT_ID: str = os.environ["WHOOP_CLIENT_ID"]
WHOOP_CLIENT_SECRET: str = os.environ["WHOOP_CLIENT_SECRET"]
WHOOP_AUTH_URL = "https://api.prod.whoop.com/oauth/oauth2/auth"
WHOOP_TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"
WHOOP_API_BASE = "https://api.prod.whoop.com/developer/v2"
WHOOP_SCOPES = "read:recovery read:sleep read:workout read:cycles read:profile read:body_measurement offline"

# --- Oura ---
OURA_CLIENT_ID: str = os.environ["OURA_CLIENT_ID"]
OURA_CLIENT_SECRET: str = os.environ["OURA_CLIENT_SECRET"]
OURA_AUTH_URL = "https://cloud.ouraring.com/oauth/authorize"
OURA_TOKEN_URL = "https://api.ouraring.com/oauth/token"
OURA_API_BASE = "https://api.ouraring.com/v2/usercollection"
OURA_SCOPES = "daily email personal heartrate workout tag session spo2"

# --- OAuth callback ---
OAUTH_REDIRECT_HOST: str = os.getenv("OAUTH_REDIRECT_HOST", "http://localhost:8080")
OAUTH_REDIRECT_URI_WHOOP = f"{OAUTH_REDIRECT_HOST}/callback/whoop"
OAUTH_REDIRECT_URI_OURA = f"{OAUTH_REDIRECT_HOST}/callback/oura"

# --- Anthropic ---
ANTHROPIC_API_KEY: str = os.environ["ANTHROPIC_API_KEY"]
CLAUDE_MODEL = "claude-opus-4-6"

# --- Database ---
DATABASE_PATH = Path(os.getenv("DATABASE_PATH", "./data/health.db"))
DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

# --- Scheduler ---
MORNING_SUMMARY_HOUR = 6
MORNING_SUMMARY_MINUTE = 0
