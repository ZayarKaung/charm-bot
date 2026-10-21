"""Command handlers for Charm Bot."""

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

from config import ADMIN_USER_ID, FREE_DAILY_LIMIT
from engine.stickers import fetch_sticker_pack, parse_pack_name
from models.user import BOT_GENDERS, DEFAULT_BOT_NAME, MODES
from telegram.helpers import escape_markdown
from utils.language import resolve_language
from utils.rate_limiter import check_rate_limit
from utils.helpers import (
    format_help_message,
    format_limit_exceeded,
    format_premium_info,
    format_profile,
    format_welcome_message,
)

logger = logging.getLogger(__name__)

# Language display names
LANGUAGES = {
    "auto": "🤖 Auto-detect",
    "en": "🇬🇧 English",
    "mm": "🇲🇲 မြန်မာ",
}


async def _user_language(db, user) -> str:
    """Resolve the language to use for a user's button-driven content."""
    user_data = await db.get_user(user.id)
    preference = (user_data or {}).get("language_preference", "auto")
    return resolve_language(preference, None, getattr(user, "language_code", None))


def get_persistent_keyboard() -> ReplyKeyboardMarkup:
    """Build the persistent bottom reply keyboard for quick access."""
    return ReplyKeyboardMarkup(
        [
            ["💬 Chat", "😂 Funny", "💕 Lovely"],
            ["😏 Pickup Line", "🎭 Jokes List"],
            ["⚙️ Settings", "👤 Profile", "⭐ Premium"],
            ["🌐 Language", "🧹 New Chat"],
        ],
        resize_keyboard=True,
        input_field_placeholder="Message Yoyo...",
    )


def _t(lang: str, en: str, mm: str) -> str:
    """Pick the English or Myanmar version of an interface string."""
    return mm if lang == "mm" else en


# Quick nickname choices offered during setup (what the bot calls the user).
NICKNAME_PRESETS = ["ကိုကို", "မမ", "ညီလေး", "ညီမလေး", "Babe", "Dear"]


def _gender_keyboard(suffix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(label, callback_data=f"gender_{key}_{suffix}")
        for key, label in BOT_GENDERS.items()
    ]])


def _nickname_keyboard(lang: str, suffix: str) -> InlineKeyboardMarkup:
    presets = [
        InlineKeyboardButton(name, callback_data=f"nick_p{index}_{suffix}")
        for index, name in enumerate(NICKNAME_PRESETS)
    ]
    return InlineKeyboardMarkup([
        presets[:3], presets[3:],
        [InlineKeyboardButton(_t(lang, "📛 Use my Telegram name", "📛 Telegram နာမည်နဲ့ ခေါ်ပါ"), callback_data=f"nick_name_{suffix}")],
        [InlineKeyboardButton(_t(lang, "✏️ Type my own", "✏️ ကိုယ်တိုင် ရိုက်ထည့်မယ်"), callback_data=f"nick_custom_{suffix}")],
    ])


def _mode_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(label, callback_data=f"mode_{mode}") for mode, label in MODES.items()
    ]])


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start — welcome the user, then set up Yoyo's identity and nickname."""
    user = update.effective_user
    db = context.bot_data["db"]

    await db.get_or_create_user(user.id, user.username or "", user.first_name or "Friend")
    lang = await _user_language(db, user)

    await update.message.reply_text(
        format_welcome_message(user.first_name or "Friend"),
        reply_markup=get_persistent_keyboard(),
        parse_mode="Markdown",
    )
    await update.message.reply_text(
        _t(lang, "First, who should Yoyo be?", "အရင်ဆုံး Yoyo ကို ဘယ်လိုပုံစံ ဖြစ်စေချင်လဲ?"),
        reply_markup=_gender_keyboard("o"),
    )
    logger.info("User started: %s", user.id)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command — show all available commands."""
    await update.message.reply_text(
        format_help_message(),
        parse_mode="Markdown",
    )


async def lovely_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _switch_mode(update, context, "lovely")


async def funny_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _switch_mode(update, context, "funny")


# Older command names kept as shortcuts.
romance_command = lovely_command
jokes_command = funny_command


async def pickup_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /pickup command — send a random pickup line."""
    user = update.effective_user
    db = context.bot_data["db"]
    romance_engine = context.bot_data["romance_engine"]

    await db.get_or_create_user(user.id, user.username or "", user.first_name or "Friend")

    allowed, _ = await check_rate_limit(db, user.id, FREE_DAILY_LIMIT)
    if not allowed:
        await update.message.reply_text(format_limit_exceeded(FREE_DAILY_LIMIT), parse_mode="Markdown")
        return

    lang = await _user_language(db, user)

    # Style selection keyboard — callback data carries the resolved language
    # so the follow-up tap serves content in the same language.
    styles = [
        [("💕 Sweet", "sweet"), ("🧀 Cheesy", "cheesy")],
        [("🧠 Clever", "clever"), ("😂 Funny", "funny")],
        [("🎲 Random", "random")],
    ]
    keyboard = [
        [
            InlineKeyboardButton(label, callback_data=f"pickup_{style}_{lang}")
            for label, style in row
        ]
        for row in styles
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    line = romance_engine.get_random_pickup_line(lang=lang)
    header = (
        "😏 *သင့်အတွက် ပိုက်အပ်လိုင်း:*" if lang == "mm"
        else "😏 *Here's a pickup line for you:*"
    )
    footer = (
        "_စတိုင်တစ်ခု ရွေးချယ်လိုပါသလား? အောက်တွင် နှိပ်ပါ:_" if lang == "mm"
        else "_Want a specific style? Pick below:_"
    )
    await update.message.reply_text(
        f"{header}\n\n{escape_markdown(line)}\n\n{footer}",
        reply_markup=reply_markup,
        parse_mode="Markdown",
    )

    await db.increment_usage(user.id)


async def category_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /category command — show joke categories."""
    user = update.effective_user
    db = context.bot_data["db"]
    jokes_engine = context.bot_data["jokes_engine"]

    await db.get_or_create_user(user.id, user.username or "", user.first_name or "Friend")
    lang = await _user_language(db, user)
    categories = jokes_engine.get_categories(lang)

    # Build keyboard from available categories. Callback data carries the
    # language suffix so the joke is served in the user's language.
    keyboard = []
    row = []
    for key, display_name in categories.items():
        row.append(InlineKeyboardButton(display_name, callback_data=f"cat_{key}_{lang}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    # Add random option
    random_label = "🎲 ကျပန်းဟာသ" if lang == "mm" else "🎲 Random Joke"
    keyboard.append(
        [InlineKeyboardButton(random_label, callback_data=f"cat_random_{lang}")]
    )

    reply_markup = InlineKeyboardMarkup(keyboard)
    title = "🎭 *ဟာသအမျိုးအစား ရွေးချယ်ပါ:*" if lang == "mm" else "🎭 *Choose a Joke Category:*"
    await update.message.reply_text(
        title,
        reply_markup=reply_markup,
        parse_mode="Markdown",
    )


async def premium_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /premium command — show premium plans."""
    await update.message.reply_text(
        format_premium_info(),
        parse_mode="Markdown",
    )


async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /profile command — show user profile and stats."""
    user = update.effective_user
    db = context.bot_data["db"]

    await db.get_or_create_user(user.id, user.username or "", user.first_name or "Friend")
    await db.reset_usage_if_needed(user.id)
    user_data = await db.get_user(user.id)

    await update.message.reply_text(
        format_profile(user_data, FREE_DAILY_LIMIT),
        parse_mode="Markdown",
    )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline keyboard button presses."""
    query = update.callback_query
    await query.answer()

    user = query.from_user
    db = context.bot_data["db"]
    data = query.data
    if not isinstance(data, str):
        return

    if data.startswith(("pickup_", "cat_")):
        await db.get_or_create_user(user.id, user.username or "", user.first_name or "Friend")
        allowed, _ = await check_rate_limit(db, user.id, FREE_DAILY_LIMIT)
        if not allowed:
            await query.edit_message_text(format_limit_exceeded(FREE_DAILY_LIMIT), parse_mode="Markdown")
            return

    # Mode selection
    if data.startswith("mode_"):
        mode = data.removeprefix("mode_")
        if mode not in MODES:
            return
        await db.get_or_create_user(user.id, user.username or "", user.first_name or "Friend")
        await db.update_user_mode(user.id, mode)
        lang = await _user_language(db, user)
        await query.edit_message_text(_mode_switched_text(mode, lang))

    elif data.startswith(("gender_", "nick_", "set_")):
        await _settings_callback(query, context, data)

    # Pickup line style
    elif data.startswith("pickup_"):
        style = data.removeprefix("pickup_")
        lang = "en"
        if style.endswith(("_en", "_mm")):
            style, lang = style.rsplit("_", 1)
        romance_engine = context.bot_data["romance_engine"]
        line = romance_engine.get_random_pickup_line(style=style, lang=lang)

        header = "😏 *ပိုက်အပ်လိုင်း:*" if lang == "mm" else "😏 *Pickup Line:*"
        await query.edit_message_text(
            f"{header}\n\n{escape_markdown(line)}",
            parse_mode="Markdown",
        )

        await db.increment_usage(user.id)

    # Joke category
    elif data.startswith("cat_"):
        category = data.removeprefix("cat_")
        lang = "en"
        if category.endswith(("_en", "_mm")):
            category, lang = category.rsplit("_", 1)
        jokes_engine = context.bot_data["jokes_engine"]
        joke = jokes_engine.get_random_joke(category=category, lang=lang)

        names = jokes_engine.CATEGORY_NAMES_MM if lang == "mm" else jokes_engine.CATEGORY_NAMES
        cat_name = names.get(category, "🎲 Random / အထွေထွေ")
        await query.edit_message_text(
            f"🎭 *{cat_name}*\n\n{escape_markdown(joke)}",
            parse_mode="Markdown",
        )

        await db.increment_usage(user.id)

    # Language selection
    elif data.startswith("lang_"):
        lang = data.removeprefix("lang_")
        if lang not in LANGUAGES:
            return
        await db.get_or_create_user(user.id, user.username or "", user.first_name or "Friend")
        await db.update_user_language(user.id, lang)

        lang_display = LANGUAGES[lang]
        await query.edit_message_text(
            f"✅ *Language set to {lang_display}!*\n\n"
            f"{'I will auto-detect your language from messages.' if lang == 'auto' else f'All responses will be in {lang_display}.'} 💬",
            parse_mode="Markdown",
        )


async def lang_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /lang command — choose response language."""
    user = update.effective_user
    db = context.bot_data["db"]

    user_data = await db.get_or_create_user(user.id, user.username or "", user.first_name or "Friend")
    current_lang = user_data.get("language_preference", "auto")
    current_display = LANGUAGES.get(current_lang, "🤖 Auto-detect")

    keyboard = [
        [
            InlineKeyboardButton("🤖 Auto-detect", callback_data="lang_auto"),
        ],
        [
            InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"),
            InlineKeyboardButton("🇲🇲 မြန်မာ", callback_data="lang_mm"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"🌐 *Language Settings*\n\n"
        f"Current: {current_display}\n\n"
        f"Choose your preferred language below:",
        reply_markup=reply_markup,
        parse_mode="Markdown",
    )


async def chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _switch_mode(update, context, "chat")


def _mode_switched_text(mode: str, lang: str) -> str:
    return _t(
        lang,
        f"{MODES[mode]} mode on. Talk to me about anything! 💬",
        f"{MODES[mode]} mode ပြောင်းပြီးပါပြီ။ ဘာမဆို ပြောလို့ရပါတယ် 💬",
    )


async def _switch_mode(update: Update, context: ContextTypes.DEFAULT_TYPE, mode: str) -> None:
    user = update.effective_user
    db = context.bot_data["db"]
    await db.get_or_create_user(user.id, user.username or "", user.first_name or "Friend")
    await db.update_user_mode(user.id, mode)
    lang = await _user_language(db, user)
    await update.message.reply_text(_mode_switched_text(mode, lang), reply_markup=get_persistent_keyboard())


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await context.bot_data["db"].clear_conversation(update.effective_chat.id, update.effective_user.id)
    await update.message.reply_text("Conversation memory cleared. Let's start fresh!", reply_markup=get_persistent_keyboard())


# --- Yoyo identity, nickname and settings ---

def _lang_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🤖 Auto-detect", callback_data="lang_auto")],
        [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"),
         InlineKeyboardButton("🇲🇲 မြန်မာ", callback_data="lang_mm")],
    ])


async def _ask_mode(message, lang: str) -> None:
    await message.reply_text(
        _t(lang, "All set! Now choose a mode:", "အားလုံး အဆင်သင့်ပါ! Mode တစ်ခု ရွေးပါ:"),
        reply_markup=_mode_keyboard(),
    )


async def _settings_callback(query, context: ContextTypes.DEFAULT_TYPE, data: str) -> None:
    """Handle gender_*, nick_* and set_* buttons from /start and /settings."""
    user = query.from_user
    db = context.bot_data["db"]
    user_data = await db.get_or_create_user(user.id, user.username or "", user.first_name or "Friend")
    lang = await _user_language(db, user)
    bot_name = user_data.get("bot_name") or DEFAULT_BOT_NAME
    kind, _, rest = data.partition("_")
    choice, _, suffix = rest.rpartition("_")
    onboarding = suffix == "o"

    if kind == "gender" and choice in BOT_GENDERS:
        await db.update_user_field(user.id, "bot_gender", choice)
        await query.edit_message_text(_t(
            lang, f"✅ {bot_name} is now {BOT_GENDERS[choice]}.",
            f"✅ {bot_name} ကို {BOT_GENDERS[choice]} အဖြစ် ပြောင်းပြီးပါပြီ။",
        ))
        if onboarding:
            await query.message.reply_text(
                _t(lang, f"What should {bot_name} call you?", f"{bot_name} က မင်းကို ဘယ်လို ခေါ်ပေးရမလဲ?"),
                reply_markup=_nickname_keyboard(lang, "o"),
            )

    elif kind == "nick":
        if choice == "custom":
            await db.update_user_field(user.id, "pending_input", "nickname_o" if onboarding else "nickname")
            await query.edit_message_text(_t(
                lang, "Type the name you want me to call you:", "ခေါ်စေချင်တဲ့ နာမည်ကို ရိုက်ပို့ပေးပါ:"
            ))
            return
        if choice == "name":
            nickname = user.first_name or "Friend"
        elif choice[1:].isdigit() and int(choice[1:]) < len(NICKNAME_PRESETS):
            nickname = NICKNAME_PRESETS[int(choice[1:])]
        else:
            return
        await db.update_user_field(user.id, "nickname", nickname)
        await query.edit_message_text(_t(lang, f"✅ I'll call you {nickname} 💕", f"✅ {nickname} လို့ ခေါ်ပေးမယ်နော် 💕"))
        if onboarding:
            await _ask_mode(query.message, lang)

    elif kind == "set":
        if rest == "gender":
            await query.edit_message_text(
                _t(lang, f"Who should {bot_name} be?", f"{bot_name} ကို ဘယ်လိုပုံစံ ဖြစ်စေချင်လဲ?"),
                reply_markup=_gender_keyboard("s"),
            )
        elif rest == "nick":
            await query.edit_message_text(
                _t(lang, f"What should {bot_name} call you?", f"{bot_name} က မင်းကို ဘယ်လို ခေါ်ပေးရမလဲ?"),
                reply_markup=_nickname_keyboard(lang, "s"),
            )
        elif rest == "name":
            await db.update_user_field(user.id, "pending_input", "bot_name")
            await query.edit_message_text(_t(lang, "Type my new name:", "ကိုယ့်အတွက် နာမည်အသစ်ကို ရိုက်ပို့ပေးပါ:"))
        elif rest == "lang":
            await query.edit_message_text("🌐 Language / ဘာသာစကား:", reply_markup=_lang_keyboard())


async def handle_pending_input(update: Update, context: ContextTypes.DEFAULT_TYPE, user_data: dict, text: str) -> bool:
    """Save a typed nickname or bot name the user was asked for. Returns True if handled."""
    pending = user_data.get("pending_input")
    if not pending:
        return False
    db = context.bot_data["db"]
    user = update.effective_user
    lang = await _user_language(db, user)
    value = " ".join(text.split())[:32]
    await db.update_user_field(user.id, "pending_input", None)
    if not value:
        return True
    if pending.startswith("nickname"):
        await db.update_user_field(user.id, "nickname", value)
        await update.message.reply_text(_t(lang, f"✅ I'll call you {value} 💕", f"✅ {value} လို့ ခေါ်ပေးမယ်နော် 💕"))
        if pending == "nickname_o":
            await _ask_mode(update.message, lang)
    elif pending == "bot_name":
        await db.update_user_field(user.id, "bot_name", value)
        await update.message.reply_text(_t(lang, f"✅ My name is now {value}!", f"✅ ကိုယ့်နာမည် {value} ဖြစ်သွားပါပြီ!"))
    return True


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the user's bot settings with buttons to change them."""
    user = update.effective_user
    db = context.bot_data["db"]
    user_data = await db.get_or_create_user(user.id, user.username or "", user.first_name or "Friend")
    lang = await _user_language(db, user)
    bot_name = user_data.get("bot_name") or DEFAULT_BOT_NAME
    gender = BOT_GENDERS.get(user_data.get("bot_gender") or "neutral", BOT_GENDERS["neutral"])
    nickname = user_data.get("nickname") or user.first_name or "-"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(_t(lang, "👤 Bot gender", "👤 Bot ပုံစံ"), callback_data="set_gender"),
         InlineKeyboardButton(_t(lang, "📛 My nickname", "📛 ကိုယ့်ခေါ်ပုံ"), callback_data="set_nick")],
        [InlineKeyboardButton(_t(lang, "✏️ Rename bot", "✏️ Bot နာမည်ပြောင်း"), callback_data="set_name"),
         InlineKeyboardButton("🌐 Language", callback_data="set_lang")],
    ])
    await update.message.reply_text(
        _t(lang, "⚙️ Settings", "⚙️ ဆက်တင်များ")
        + f"\n\n🤖 {bot_name} · {gender}\n📛 " + _t(lang, "Calls you: ", "ခေါ်ပုံ: ") + nickname,
        reply_markup=keyboard,
    )


async def rename_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/rename <name> — give the bot a new name for this user."""
    user = update.effective_user
    db = context.bot_data["db"]
    user_data = await db.get_or_create_user(user.id, user.username or "", user.first_name or "Friend")
    name = " ".join(context.args or [])
    if not name:
        await db.update_user_field(user.id, "pending_input", "bot_name")
        lang = await _user_language(db, user)
        await update.message.reply_text(_t(lang, "Type my new name:", "ကိုယ့်အတွက် နာမည်အသစ်ကို ရိုက်ပို့ပေးပါ:"))
        return
    await handle_pending_input(update, context, {**user_data, "pending_input": "bot_name"}, name)


async def memory_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/memory — show the long-term facts remembered about the user."""
    db = context.bot_data["db"]
    user = update.effective_user
    lang = await _user_language(db, user)
    facts = await db.get_facts(update.effective_chat.id, user.id)
    if not facts:
        await update.message.reply_text(_t(lang, "I don't remember any facts about you yet.", "မင်းအကြောင်း မှတ်ထားတာ မရှိသေးပါဘူး။"))
        return
    await update.message.reply_text(
        _t(lang, "🧠 What I remember about you:", "🧠 မင်းအကြောင်း မှတ်ထားတာတွေ:")
        + "\n\n" + "\n".join(f"• {fact}" for fact in facts)
        + "\n\n" + _t(lang, "Use /forget to erase everything.", "အားလုံးဖျက်ချင်ရင် /forget ကို သုံးပါ။")
    )


async def forget_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/forget — erase long-term facts and recent conversation for this chat."""
    db = context.bot_data["db"]
    user = update.effective_user
    await db.clear_facts(update.effective_chat.id, user.id)
    await db.clear_conversation(update.effective_chat.id, user.id)
    lang = await _user_language(db, user)
    await update.message.reply_text(_t(lang, "🧹 I've forgotten everything about you.", "🧹 မင်းအကြောင်း အားလုံး ဖျက်လိုက်ပါပြီ။"))


async def myid_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/myid — show the user's Telegram ID (needed for ADMIN_USER_ID)."""
    await update.message.reply_text(f"🆔 Your Telegram user ID: {update.effective_user.id}")


async def addpack_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/addpack <link or name> — admin only: load a sticker pack the bot can reply with."""
    if not ADMIN_USER_ID or update.effective_user.id != ADMIN_USER_ID:
        await update.message.reply_text("⛔ Only the bot admin can add sticker packs. (Set ADMIN_USER_ID in .env; see /myid.)")
        return
    name = parse_pack_name(" ".join(context.args or []))
    if not name:
        await update.message.reply_text("Usage: /addpack https://t.me/addstickers/PackName")
        return
    try:
        stickers = await fetch_sticker_pack(context.bot, name)
    except Exception as error:
        await update.message.reply_text(f"❌ Couldn't load sticker pack '{name}': {error}")
        return
    db = context.bot_data["db"]
    await db.save_stickers(name, stickers)
    context.bot_data["stickers"].load(await db.get_stickers())
    packs = await db.get_sticker_packs()
    await update.message.reply_text(f"✅ Added '{name}' ({len(stickers)} stickers). Packs: {', '.join(packs)}")
