"""Message handler for Charm Bot — routes text, stickers and photos to the AI companion."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from config import FREE_DAILY_LIMIT
from engine.ai_provider import parse_reply
from models.user import normalize_mode
from utils.helpers import format_limit_exceeded
from utils.language import explicit_language, resolve_language, to_unicode
from utils.rate_limiter import check_rate_limit

logger = logging.getLogger(__name__)

# Images larger than this are described in text only.
MAX_IMAGE_BYTES = 4 * 1024 * 1024

# Persistent keyboard button text -> action mapping
BUTTON_ACTIONS = {
    "💬 Chat": "switch_chat",
    "😂 Funny": "switch_funny",
    "💕 Lovely": "switch_lovely",
    "😏 Pickup Line": "pickup",
    "🎭 Jokes List": "category",
    "⚙️ Settings": "settings",
    "👤 Profile": "profile",
    "⭐ Premium": "premium",
    "🌐 Language": "language",
    "🧹 New Chat": "reset",
}


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Text messages: keyboard buttons, pending setting input, or conversation."""
    from handlers.commands import handle_pending_input

    user = update.effective_user
    message_text = update.message.text
    if not message_text:
        return

    db = context.bot_data["db"]
    user_data = await db.get_or_create_user(user.id, user.username or "", user.first_name or "Friend")

    # Check if it's a persistent keyboard button tap
    action = BUTTON_ACTIONS.get(message_text)
    if action:
        if user_data.get("pending_input"):
            await db.update_user_field(user.id, "pending_input", None)
        await _handle_button_action(action, update, context)
        return

    if await handle_pending_input(update, context, user_data, message_text):
        return

    await _converse(update, context, user_data, to_unicode(message_text))


async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Stickers and photos: describe them for the AI, and let Gemini see the image."""
    message = update.message
    user = update.effective_user
    db = context.bot_data["db"]
    user_data = await db.get_or_create_user(user.id, user.username or "", user.first_name or "Friend")
    caption = to_unicode(message.caption or "")

    file_id, mime = None, "image/jpeg"
    if message.sticker:
        sticker = message.sticker
        kind = "animated sticker" if sticker.is_animated else "video sticker" if sticker.is_video else "sticker"
        description = f"[The user sent a {kind}: {sticker.emoji or '?'}"
        if sticker.set_name:
            description += f" from pack \"{sticker.set_name}\""
        description += "]"
        if sticker.is_animated or sticker.is_video:
            file_id = sticker.thumbnail.file_id if sticker.thumbnail else None
        else:
            file_id, mime = sticker.file_id, "image/webp"
    elif message.photo:
        photo = message.photo[-1]
        description = "[The user sent a photo]"
        if photo.file_size is None or photo.file_size <= MAX_IMAGE_BYTES:
            file_id = photo.file_id
    else:
        return
    if caption:
        description += " " + caption

    image = await _download_image(context, file_id, mime) if file_id else None
    await _converse(update, context, user_data, description, image=image)


async def _download_image(context, file_id: str, mime: str) -> tuple[bytes, str] | None:
    """Fetch a Telegram file for Gemini; on failure the text description is enough."""
    try:
        telegram_file = await context.bot.get_file(file_id)
        data = bytes(await telegram_file.download_as_bytearray())
    except Exception as error:
        logger.warning("Could not download media for the AI: %s", error)
        return None
    if len(data) > MAX_IMAGE_BYTES:
        return None
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        mime = "image/webp"
    elif data[:3] == b"\xff\xd8\xff":
        mime = "image/jpeg"
    elif data[:8] == b"\x89PNG\r\n\x1a\n":
        mime = "image/png"
    return data, mime


async def _converse(update: Update, context: ContextTypes.DEFAULT_TYPE, user_data: dict,
                    user_text: str, image: tuple[bytes, str] | None = None) -> None:
    """One conversational turn: quota, AI reply, optional sticker, memory, usage."""
    user = update.effective_user
    chat_id = update.effective_chat.id
    db = context.bot_data["db"]
    ai_provider = context.bot_data["ai_provider"]

    allowed, remaining = await check_rate_limit(db, user.id, FREE_DAILY_LIMIT)
    if not allowed:
        await update.message.reply_text(format_limit_exceeded(FREE_DAILY_LIMIT), parse_mode="Markdown")
        return

    # Determine language: an explicit /lang choice wins, else auto-detect.
    lang_pref = user_data.get("language_preference", "auto")
    lang = resolve_language(lang_pref, user_text if not user_text.startswith("[") else None,
                            getattr(user, "language_code", None))
    # Only force the AI's output language when the user actually chose one;
    # on 'auto' we let the model mirror the user's own wording.
    forced_lang = explicit_language(lang_pref)

    history = await db.get_conversation(chat_id, user.id)
    persona = {
        "bot_name": user_data.get("bot_name"),
        "bot_gender": user_data.get("bot_gender"),
        "nickname": user_data.get("nickname"),
        "facts": await db.get_facts(chat_id, user.id),
        "sticker_emoji": context.bot_data["stickers"].emojis() if "stickers" in context.bot_data else [],
    }
    response = None
    if ai_provider.is_available():
        bot = getattr(context, "bot", None)
        if bot is not None:
            try:
                await bot.send_chat_action(chat_id, "typing")
            except Exception:
                pass
        response = await ai_provider.generate_response(
            user_text, mode=normalize_mode(user_data.get("mode")),
            user_name=user.first_name or "", lang=forced_lang, history=history,
            persona=persona, image=image,
        )
    text, sticker_emoji, facts = parse_reply(response or "")
    sticker_id = context.bot_data["stickers"].pick(sticker_emoji) if "stickers" in context.bot_data else None
    if not text and not sticker_id:
        notice = (
            "AI ချိတ်ဆက်မှု ခေတ္တမရနိုင်ပါ။ ခဏနေ ပြန်ကြိုးစားပါ။ "
            "မက်ဆေ့အသုံးပြုခွင့် မလျှော့ထားပါ။ /pickup နဲ့ /category ကို သုံးနိုင်ပါတယ်။"
            if lang == "mm" else
            "AI chat is temporarily unavailable. Please try again shortly. "
            "This did not use your message allowance. You can still use /pickup or /category."
        )
        await update.message.reply_text(notice)
        logger.warning("No AI conversation reply; check provider credentials, model access and quota")
        return

    text = text[:4000]
    shown = text
    # Add remaining count for free users (occasionally)
    if text and not user_data["is_premium"] and 0 < remaining <= 3:
        if lang == "mm":
            shown += f"\n\n(ဒီနေ့ အခမဲ့ မက်ဆေ့ {remaining - 1} ခု ကျန်ပါသည်)"
        else:
            shown += f"\n\n({remaining - 1} free messages left today)"

    if text:
        await update.message.reply_text(shown)
    sticker_sent = False
    if sticker_id:
        try:
            await update.message.reply_sticker(sticker_id)
            sticker_sent = True
        except Exception as error:
            logger.warning("Could not send reply sticker: %s", error)
            if not text:
                raise

    # Store what the user actually saw, so follow-ups stay consistent.
    assistant_text = text + (f"\n[sticker: {sticker_emoji}]" if sticker_sent else "")
    await db.save_conversation_turn(chat_id, user.id, user_text, assistant_text.strip())
    if facts:
        await db.add_facts(chat_id, user.id, facts)
    await db.increment_usage(user.id)


async def _handle_button_action(action: str, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle taps on persistent reply keyboard buttons."""
    # Import here to avoid circular imports
    from handlers.commands import (
        category_command,
        chat_command,
        funny_command,
        lang_command,
        lovely_command,
        pickup_command,
        premium_command,
        profile_command,
        reset_command,
        settings_command,
    )

    action_map = {
        "switch_chat": chat_command,
        "switch_funny": funny_command,
        "switch_lovely": lovely_command,
        "pickup": pickup_command,
        "category": category_command,
        "settings": settings_command,
        "profile": profile_command,
        "premium": premium_command,
        "language": lang_command,
        "reset": reset_command,
    }

    handler = action_map.get(action)
    if handler:
        await handler(update, context)
