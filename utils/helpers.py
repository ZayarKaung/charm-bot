"""Utility helper functions for Charm Bot."""

from models.user import BOT_GENDERS, DEFAULT_BOT_NAME, get_mode_display
from telegram.helpers import escape_markdown

# Language display names
LANG_DISPLAY = {
    "auto": "🤖 Auto-detect",
    "en": "🇬🇧 English",
    "mm": "🇲🇲 မြန်မာ",
}


def format_welcome_message(first_name: str) -> str:
    """Format the welcome message for new users."""
    return (
        f"Hey {escape_markdown(first_name)}! 👋 I'm *Yoyo*, your AI companion 🤖\n"
        f"မင်္ဂလာပါ! ကိုယ်က *Yoyo* ပါ — မင်းရဲ့ AI သူငယ်ချင်းပေါ့ 💬\n\n"
        f"Talk to me like a friend, in မြန်မာ or English. I understand emoji, "
        f"stickers and photos too.\n\n"
        f"💬 *Chat* — friendly everyday talk\n"
        f"😂 *Funny* — jokes, banter and teasing\n"
        f"💕 *Lovely* — sweet and romantic\n\n"
        f"I remember our recent chat and important things you tell me "
        f"(/memory to see, /forget to erase)."
    )


def format_help_message() -> str:
    """Format the help message with all available commands."""
    return (
        "📖 *Yoyo Commands*\n\n"
        "🔀 *Modes:*\n"
        "/chat — Friendly conversation 💬\n"
        "/funny — Jokes and banter 😂\n"
        "/lovely — Sweet and romantic 💕\n\n"
        "⚙️ *Settings:*\n"
        "/settings — Bot gender, your nickname, bot name\n"
        "/rename — Give the bot a new name ✏️\n"
        "/lang — Language (English / Myanmar / Auto) 🌐\n\n"
        "🧠 *Memory:*\n"
        "/reset — Clear recent conversation 🧹\n"
        "/memory — See what I remember\n"
        "/forget — Erase everything I remember\n\n"
        "🎲 *Extras:*\n"
        "/pickup — A random pickup line 😏\n"
        "/category — Jokes by category 🎭\n\n"
        "👤 *Account:*\n"
        "/profile — Your profile & usage 📊\n"
        "/premium — Premium plans ⭐\n"
        "/myid — Your Telegram ID 🆔\n"
        "/help — Show this message 📖\n\n"
        "💡 *Tip:* Just talk to me — send text, emoji, stickers or photos!"
    )


def format_profile(user_data: dict, free_limit: int) -> str:
    """Format the user profile card."""
    mode_display = get_mode_display(user_data["mode"])
    premium_status = "⭐ Premium" if user_data["is_premium"] else "🆓 Free"
    remaining = max(0, free_limit - user_data["daily_count"])
    lang_pref = user_data.get("language_preference", "auto")
    lang_display = LANG_DISPLAY.get(lang_pref, "🤖 Auto-detect")
    bot_name = user_data.get("bot_name") or DEFAULT_BOT_NAME
    gender = BOT_GENDERS.get(user_data.get("bot_gender") or "neutral", BOT_GENDERS["neutral"])
    nickname = user_data.get("nickname") or user_data["first_name"]

    usage_display = (
        "♾️ Unlimited" if user_data["is_premium"]
        else f"{user_data['daily_count']}/{free_limit} ({remaining} remaining)"
    )

    return (
        f"👤 *Your Profile*\n\n"
        f"📛 Name: {escape_markdown(user_data['first_name'])}\n"
        f"💬 Bot calls you: {escape_markdown(nickname)}\n"
        f"🤖 Bot: {escape_markdown(bot_name)} · {gender}\n"
        f"🎭 Current Mode: {mode_display}\n"
        f"🌐 Language: {lang_display}\n"
        f"💎 Status: {premium_status}\n"
        f"📊 Today's Usage: {usage_display}\n"
        f"📅 Member Since: {user_data['created_at'][:10]}\n"
    )


def format_premium_info() -> str:
    """Format premium plans information."""
    return (
        "⭐ *Yoyo Premium* ⭐\n\n"
        "🆓 *Free Plan (now):*\n"
        "• A daily free message allowance (see /profile)\n"
        "• All modes: Chat, Funny, Lovely\n"
        "• Memory, stickers and photos\n\n"
        "💎 *Premium (coming soon):*\n"
        "• Unlimited messages\n\n"
        "🚀 _Payments are not available yet. Stay tuned!_ 💕"
    )


def format_limit_exceeded(free_limit: int) -> str:
    """Format the message shown when free usage limit is exceeded."""
    return (
        f"⏳ *Daily Limit Reached!*\n\n"
        f"You've used all {free_limit} free messages for today.\n\n"
        f"🔄 Your limit resets at midnight.\n\n"
        f"Want unlimited messages? Check out /premium ⭐\n"
        f"Or come back tomorrow! We'll miss you 💕"
    )
