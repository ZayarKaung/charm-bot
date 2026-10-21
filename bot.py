"""
Charm Bot — "Yoyo", an AI companion for Telegram
================================================

Natural conversation in Myanmar and English, with Chat, Funny and Lovely
modes, long-term memory, and sticker/photo understanding.

Usage:
    1. Copy .env.example to .env
    2. Add your TELEGRAM_BOT_TOKEN (from @BotFather)
    3. Optionally add GEMINI_API_KEY (from https://aistudio.google.com)
    4. Run: python bot.py
"""

import logging
import sys

from telegram import BotCommand
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from config import (
    BOT_NAME, DATA_DIR, DB_PATH, GEMINI_API_KEY, GROQ_API_KEY, STICKER_PACKS, TELEGRAM_BOT_TOKEN,
)
from engine.ai_provider import AIProvider
from engine.jokes import JokesEngine
from engine.romance import RomanceEngine
from engine.stickers import StickerLibrary, fetch_sticker_pack
from handlers.commands import (
    addpack_command,
    button_callback,
    category_command,
    chat_command,
    forget_command,
    funny_command,
    help_command,
    jokes_command,
    lang_command,
    lovely_command,
    memory_command,
    myid_command,
    pickup_command,
    premium_command,
    profile_command,
    rename_command,
    reset_command,
    romance_command,
    settings_command,
    start_command,
)
from handlers.messages import handle_media, handle_message
from handlers.payments import premium_checkout
from models.database import Database

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def post_init(application: Application) -> None:
    """Initialize shared resources after the bot application starts."""
    # Initialize database
    db = Database(DB_PATH)
    await db.connect()
    application.bot_data["db"] = db

    # Initialize engines
    romance_engine = RomanceEngine(DATA_DIR)
    jokes_engine = JokesEngine(DATA_DIR)
    application.bot_data["romance_engine"] = romance_engine
    application.bot_data["jokes_engine"] = jokes_engine

    # Initialize AI provider
    ai_provider = AIProvider(GEMINI_API_KEY, GROQ_API_KEY)
    application.bot_data["ai_provider"] = ai_provider

    # Reply stickers: fetch configured packs that aren't cached in the database yet
    cached_packs = set(await db.get_sticker_packs())
    for pack in STICKER_PACKS:
        if pack in cached_packs:
            continue
        try:
            await db.save_stickers(pack, await fetch_sticker_pack(application.bot, pack))
        except Exception as error:
            logger.warning("Could not load sticker pack %s: %s", pack, error)
    stickers = StickerLibrary()
    stickers.load(await db.get_stickers())
    application.bot_data["stickers"] = stickers

    # Set bot commands (shown in Telegram's menu)
    commands = [
        BotCommand("start", "👋 Start / set up Yoyo"),
        BotCommand("chat", "💬 Normal conversation"),
        BotCommand("funny", "😂 Funny mode"),
        BotCommand("lovely", "💕 Lovely (romantic) mode"),
        BotCommand("settings", "⚙️ Bot gender, nickname, name"),
        BotCommand("lang", "🌐 Choose language"),
        BotCommand("reset", "🧹 Clear recent conversation"),
        BotCommand("memory", "🧠 What Yoyo remembers"),
        BotCommand("forget", "🗑 Forget everything about me"),
        BotCommand("pickup", "😏 Get a pickup line"),
        BotCommand("category", "🎭 Choose joke category"),
        BotCommand("profile", "📊 View your profile"),
        BotCommand("premium", "⭐ Premium plans"),
        BotCommand("myid", "🆔 Show my Telegram ID"),
        BotCommand("help", "📖 Show all commands"),
    ]
    await application.bot.set_my_commands(commands)

    # Status report
    ai_status = "✅ Configured (Gemini/Groq)" if ai_provider.is_available() else "❌ Disabled (no API key)"
    user_count = await db.get_user_count()

    logger.info("=" * 50)
    logger.info("🌹😂 %s is starting up!", BOT_NAME)
    logger.info("=" * 50)
    logger.info("🤖 AI Responses: %s", ai_status)
    logger.info("👥 Registered Users: %d", user_count)
    logger.info("🎨 Reply stickers: %d", len(stickers))
    logger.info("📁 Data Directory: %s", DATA_DIR)
    logger.info("💾 Database: %s", DB_PATH)
    logger.info("=" * 50)
    logger.info("Bot is ready! Send /start to begin chatting.")
    logger.info("=" * 50)


async def post_shutdown(application: Application) -> None:
    """Clean up resources when the bot shuts down."""
    db = application.bot_data.get("db")
    if db:
        await db.close()
    logger.info("👋 %s has shut down.", BOT_NAME)


def main() -> None:
    """Start the Charm Bot."""
    print(f"\nStarting {BOT_NAME}...\n")

    # Build the application
    application = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # --- Register command handlers ---
    for name, handler in [
        ("start", start_command), ("help", help_command),
        ("chat", chat_command), ("funny", funny_command), ("lovely", lovely_command),
        ("jokes", jokes_command), ("romance", romance_command),
        ("settings", settings_command), ("rename", rename_command), ("lang", lang_command),
        ("reset", reset_command), ("memory", memory_command), ("forget", forget_command),
        ("pickup", pickup_command), ("category", category_command),
        ("premium", premium_command), ("profile", profile_command), ("pay", premium_checkout),
        ("myid", myid_command), ("addpack", addpack_command),
    ]:
        application.add_handler(CommandHandler(name, handler))

    # --- Register callback query handler (inline buttons) ---
    application.add_handler(CallbackQueryHandler(button_callback))

    # --- Register message handler (catch-all for text messages) ---
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )
    application.add_handler(MessageHandler(filters.Sticker.ALL | filters.PHOTO, handle_media))

    # --- Start polling ---
    print("Bot is running! Press Ctrl+C to stop.\n")
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nBot stopped by user.")
        sys.exit(0)
    except ValueError as e:
        print(f"\n{e}")
        sys.exit(1)
