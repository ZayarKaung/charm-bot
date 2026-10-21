"""Configuration module for Charm Bot."""

import os
import pathlib
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- Required ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "your_telegram_bot_token_here":
    raise ValueError(
        "❌ TELEGRAM_BOT_TOKEN is not set!\n"
        "   1. Go to Telegram and message @BotFather\n"
        "   2. Create a new bot with /newbot\n"
        "   3. Copy the token and add it to your .env file"
    )

# --- Optional AI Providers ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY == "your_gemini_api_key_here":
    GEMINI_API_KEY = None

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if GROQ_API_KEY == "your_groq_api_key_here":
    GROQ_API_KEY = None

# --- Bot Settings ---
FREE_DAILY_LIMIT = int(os.getenv("FREE_DAILY_LIMIT", "10"))
BOT_NAME = os.getenv("BOT_NAME", "Charm Bot")

# Telegram user ID allowed to run admin commands such as /addpack (see /myid).
_admin = (os.getenv("ADMIN_USER_ID") or "").strip()
ADMIN_USER_ID = int(_admin) if _admin.isdigit() else None

# Sticker packs the bot can reply with, loaded at startup (comma-separated names).
STICKER_PACKS = [
    name.strip() for name in os.getenv("STICKER_PACKS", "nkosip_mini").split(",") if name.strip()
]

# --- Paths ---
BASE_DIR = pathlib.Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = BASE_DIR / "charm_bot.db"
