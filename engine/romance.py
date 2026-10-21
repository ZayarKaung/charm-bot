"""Romance response engine for Charm Bot — supports English and Myanmar."""

import json
import logging
import random
from collections import deque
from pathlib import Path

from utils.language import detect_language

logger = logging.getLogger(__name__)


class RomanceEngine:
    """Generates romantic responses from a curated library (English + Myanmar)."""

    def __init__(self, data_dir: Path):
        self._data_dir = data_dir
        self._data = {"en": {}, "mm": {}}          # Romance data by language
        self._pickup = {"en": {}, "mm": {}}         # Pickup lines by language
        self._recent: deque = deque(maxlen=30)
        self._load_data()

    def _load_json(self, filename: str) -> dict:
        """Safely load a JSON file."""
        path = self._data_dir / filename
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            logger.info("✅ Loaded %s: %d categories", filename, len(data))
            return data
        except FileNotFoundError:
            logger.warning("⚠️ File not found: %s", path)
            return {}

    def _load_data(self) -> None:
        """Load all romance and pickup data for both languages."""
        self._data["en"] = self._load_json("romance_lines.json") or {"compliments": ["You're amazing! 💕"]}
        self._data["mm"] = self._load_json("romance_mm.json") or {}
        self._pickup["en"] = self._load_json("pickup_lines.json") or {"sweet": ["Are you a magician? ✨"]}
        self._pickup["mm"] = self._load_json("pickup_lines_mm.json") or {}

    def _pick_unique(self, items: list[str]) -> str:
        """Pick a random item, avoiding recent repeats."""
        available = [item for item in items if item not in self._recent]
        if not available:
            self._recent.clear()
            available = items
        choice = random.choice(available)
        self._recent.append(choice)
        return choice

    def _get_items(self, category: str, lang: str) -> list[str]:
        """Get items for a category, falling back to English if Myanmar is empty."""
        items = self._data.get(lang, {}).get(category, [])
        if not items:
            items = self._data.get("en", {}).get(category, [])
        return items if items else ["💕"]

    def get_random_compliment(self, lang: str = "en") -> str:
        return self._pick_unique(self._get_items("compliments", lang))

    def get_random_quote(self, lang: str = "en") -> str:
        return self._pick_unique(self._get_items("love_quotes", lang))

    def get_random_sweet_message(self, lang: str = "en") -> str:
        return self._pick_unique(self._get_items("sweet_messages", lang))

    def get_random_good_morning(self, lang: str = "en") -> str:
        return self._pick_unique(self._get_items("good_morning", lang))

    def get_random_good_night(self, lang: str = "en") -> str:
        return self._pick_unique(self._get_items("good_night", lang))

    def get_random_pickup_line(self, style: str = "random", lang: str = "en") -> str:
        """Get a random pickup line, optionally filtered by style and language."""
        pickup = self._pickup.get(lang, {})
        if not pickup:
            pickup = self._pickup.get("en", {})

        if style == "random" or style not in pickup:
            all_lines = []
            for lines in pickup.values():
                all_lines.extend(lines)
            return self._pick_unique(all_lines) if all_lines else "😏💕"
        return self._pick_unique(pickup[style])

    def get_random_romance_response(self, lang: str = "en") -> str:
        """Get a random romance response from any category."""
        data = self._data.get(lang, {})
        if not data:
            data = self._data.get("en", {})
        all_responses = []
        for items in data.values():
            all_responses.extend(items)
        return self._pick_unique(all_responses) if all_responses else "💕"

    def get_contextual_response(self, message: str, lang: str | None = None) -> str:
        """
        Pick a contextual response based on message keywords and language.

        Pass `lang` to force a language; otherwise it is detected from the message.
        """
        if lang not in ("en", "mm"):
            lang = detect_language(message)
        msg_lower = message.lower()

        # Myanmar keywords
        mm_keywords = {
            "morning": ["နံနက်", "မနက်", "ထပါ", "morning"],
            "night": ["ည", "အိပ်", "အိပ်မက်", "night"],
            "pickup": ["pickup", "line", "ပိုက်"],
            "quote": ["ချစ်", "မေတ္တာ", "အချစ်", "love"],
            "compliment": ["လှ", "ချော", "လှပ", "compliment"],
        }

        # English keywords
        en_keywords = {
            "morning": ["morning", "wake", "sunrise"],
            "night": ["night", "sleep", "dream", "bed"],
            "pickup": ["pickup", "line", "flirt"],
            "quote": ["quote", "love", "romantic"],
            "compliment": ["compliment", "pretty", "beautiful", "handsome"],
        }

        keywords = mm_keywords if lang == "mm" else en_keywords

        if any(word in msg_lower for word in keywords["morning"]):
            return self.get_random_good_morning(lang)
        elif any(word in msg_lower for word in keywords["night"]):
            return self.get_random_good_night(lang)
        elif any(word in msg_lower for word in keywords["pickup"]):
            return self.get_random_pickup_line(lang=lang)
        elif any(word in msg_lower for word in keywords["quote"]):
            return self.get_random_quote(lang)
        elif any(word in msg_lower for word in keywords["compliment"]):
            return self.get_random_compliment(lang)
        else:
            return self.get_random_romance_response(lang)
