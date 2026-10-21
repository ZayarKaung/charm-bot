"""Language detection utility for Charm Bot — detects Myanmar vs English."""

import re

# Myanmar Unicode range: U+1000 to U+109F (Myanmar block)
# Extended Myanmar: U+AA60 to U+AA7F
MYANMAR_PATTERN = re.compile(r"[\u1000-\u109F\uAA60-\uAA7F]")


def detect_language(text: str) -> str:
    """
    Detect if text is Myanmar or English.

    Returns:
        'mm' for Myanmar, 'en' for English.
    """
    if not text:
        return "en"

    myanmar_chars = len(MYANMAR_PATTERN.findall(text))
    total_alpha = sum(1 for c in text if c.isalpha())

    if total_alpha == 0:
        return "en"

    myanmar_ratio = myanmar_chars / total_alpha

    # If more than 30% of alphabetic characters are Myanmar, treat as Myanmar
    return "mm" if myanmar_ratio > 0.3 else "en"


def is_myanmar(text: str) -> bool:
    """Quick check if text contains Myanmar characters."""
    return bool(MYANMAR_PATTERN.search(text))


def resolve_language(
    preference: str | None,
    text: str | None = None,
    telegram_code: str | None = None,
) -> str:
    """
    Resolve which language to respond in.

    An explicit 'en'/'mm' preference always wins. Otherwise ('auto' or unset)
    fall back to detecting from the message text, then to the user's Telegram
    client language, then to English.
    """
    if preference in ("en", "mm"):
        return preference
    if text:
        return detect_language(text)
    if telegram_code and telegram_code.lower().startswith("my"):
        return "mm"
    return "en"


def explicit_language(preference: str | None) -> str | None:
    """Return the language the user explicitly chose, or None if auto-detecting."""
    return preference if preference in ("en", "mm") else None


# Zawgyi is a legacy Myanmar font encoding many users still type in. The AI and
# the language detector expect Unicode, so convert Zawgyi input first.
try:
    from myanmar import converter as _mm_converter
    from myanmartools import ZawgyiDetector

    _zawgyi_detector = ZawgyiDetector()
except ImportError:  # optional dependency
    _zawgyi_detector = None


def to_unicode(text: str) -> str:
    """Return text with Zawgyi-encoded Myanmar converted to Unicode."""
    if not text or _zawgyi_detector is None or not is_myanmar(text):
        return text
    try:
        if _zawgyi_detector.get_zawgyi_probability(text) > 0.95:
            return _mm_converter.convert(text, "zawgyi", "unicode")
    except Exception:
        pass
    return text
