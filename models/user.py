"""User-related constants and helpers for Charm Bot."""

# Available chat modes
MODES = {
    "chat": "💬 Chat",
    "funny": "😂 Funny",
    "lovely": "💕 Lovely",
}

DEFAULT_MODE = "chat"

# Old mode names that still arrive from /jokes, /romance or older records.
MODE_ALIASES = {"jokes": "funny", "romance": "lovely", "flirt": "chat"}

DEFAULT_BOT_NAME = "Yoyo"

BOT_GENDERS = {
    "neutral": "🤖 Neutral AI",
    "male": "👦 Male",
    "female": "👧 Female",
}


def normalize_mode(mode: str | None) -> str:
    """Map legacy or unknown mode names onto a current mode."""
    mode = MODE_ALIASES.get(mode or "", mode)
    return mode if mode in MODES else DEFAULT_MODE


def is_within_limit(daily_count: int, is_premium: bool, free_limit: int) -> bool:
    """Check if user is within their daily usage limit."""
    if is_premium:
        return True  # Premium users have unlimited access
    return daily_count < free_limit


def get_mode_display(mode: str) -> str:
    """Get the display name for a mode."""
    return MODES[normalize_mode(mode)]
