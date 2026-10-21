"""Jokes response engine for Charm Bot — supports English and Myanmar."""

import json
import logging
import random
from collections import deque
from pathlib import Path

from utils.language import detect_language

logger = logging.getLogger(__name__)


class JokesEngine:
    """Generates joke responses from a curated library (English + Myanmar)."""

    # Category display names
    CATEGORY_NAMES = {
        "one_liners": "😎 One-Liners",
        "dad_jokes": "👨 Dad Jokes",
        "puns": "🤓 Puns",
        "knock_knock": "🚪 Knock-Knock",
        "tech_jokes": "💻 Tech Jokes",
        "animal_jokes": "🐾 Animal Jokes",
        "situational": "😂 Situational",
    }

    # Myanmar category display names
    CATEGORY_NAMES_MM = {
        "one_liners": "😎 ဟာသတစ်ကြောင်း",
        "dad_jokes": "👨 အဖေ့ဟာသ",
        "puns": "🤓 စကားလုံးကစားခြင်း",
        "tech_jokes": "💻 နည်းပညာဟာသ",
        "situational": "😂 အခြေအနေဟာသ",
    }

    def __init__(self, data_dir: Path):
        self._data_dir = data_dir
        self._data = {"en": {}, "mm": {}}
        self._recent: deque = deque(maxlen=30)
        self._load_data()

    def _load_json(self, filename: str) -> dict:
        """Safely load a JSON file."""
        path = self._data_dir / filename
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            total = sum(len(v) for v in data.values())
            logger.info("✅ Loaded %s: %d categories, %d jokes", filename, len(data), total)
            return data
        except FileNotFoundError:
            logger.warning("⚠️ File not found: %s", path)
            return {}

    def _load_data(self) -> None:
        """Load jokes data for both languages."""
        self._data["en"] = self._load_json("jokes.json") or {"one_liners": ["Why did the chicken cross the road? 🐔"]}
        self._data["mm"] = self._load_json("jokes_mm.json") or {}

    def _pick_unique(self, items: list) -> str:
        """Pick a random item, avoiding recent repeats."""
        str_items = []
        for item in items:
            if isinstance(item, dict):
                str_items.append(f"{item['setup']}\n\n{item['punchline']}")
            else:
                str_items.append(item)

        available = [item for item in str_items if item not in self._recent]
        if not available:
            self._recent.clear()
            available = str_items

        choice = random.choice(available)
        self._recent.append(choice)
        return choice

    def _get_items(self, category: str, lang: str) -> list:
        """Get items for a category, falling back to English if Myanmar is empty."""
        items = self._data.get(lang, {}).get(category, [])
        if not items:
            items = self._data.get("en", {}).get(category, [])
        return items if items else ["😂"]

    def get_categories(self, lang: str = "en") -> dict[str, str]:
        """Get available joke categories with display names."""
        data = self._data.get(lang, {})
        if not data:
            data = self._data.get("en", {})
        names = self.CATEGORY_NAMES_MM if lang == "mm" else self.CATEGORY_NAMES
        return {
            key: names.get(key, key.replace("_", " ").title())
            for key in data.keys()
        }

    def get_random_one_liner(self, lang: str = "en") -> str:
        return self._pick_unique(self._get_items("one_liners", lang))

    def get_random_dad_joke(self, lang: str = "en") -> str:
        return self._pick_unique(self._get_items("dad_jokes", lang))

    def get_random_pun(self, lang: str = "en") -> str:
        return self._pick_unique(self._get_items("puns", lang))

    def get_random_knock_knock(self) -> str:
        """Knock-knock jokes are English only."""
        return self._pick_unique(self._get_items("knock_knock", "en"))

    def get_random_tech_joke(self, lang: str = "en") -> str:
        return self._pick_unique(self._get_items("tech_jokes", lang))

    def get_random_animal_joke(self) -> str:
        """Animal jokes are English only."""
        return self._pick_unique(self._get_items("animal_jokes", "en"))

    def get_random_joke(self, category: str = "random", lang: str = "en") -> str:
        """Get a random joke, optionally from a specific category."""
        data = self._data.get(lang, {})
        if not data:
            data = self._data.get("en", {})

        if category != "random" and category in data:
            return self._pick_unique(data[category])

        # Pick from all categories
        all_jokes = []
        for items in data.values():
            all_jokes.extend(items)
        return self._pick_unique(all_jokes) if all_jokes else "😂"

    def get_contextual_joke(self, message: str, lang: str | None = None) -> str:
        """
        Pick a contextual joke based on message keywords and language.

        Pass `lang` to force a language; otherwise it is detected from the message.
        """
        if lang not in ("en", "mm"):
            lang = detect_language(message)
        msg_lower = message.lower()

        # Myanmar keywords
        if lang == "mm":
            if any(word in msg_lower for word in ["code", "program", "computer", "tech", "bug", "python", "wifi", "ဖုန်း", "ကွန်ပျူတာ"]):
                return self.get_random_tech_joke(lang)
            elif any(word in msg_lower for word in ["အဖေ", "dad", "father", "သား"]):
                return self.get_random_dad_joke(lang)
            elif any(word in msg_lower for word in ["pun", "စကားလုံး", "ကစား"]):
                return self.get_random_pun(lang)
            else:
                return self.get_random_joke(lang=lang)
        else:
            if any(word in msg_lower for word in ["code", "program", "computer", "tech", "bug", "python"]):
                return self.get_random_tech_joke(lang)
            elif any(word in msg_lower for word in ["knock", "door"]):
                return self.get_random_knock_knock()
            elif any(word in msg_lower for word in ["dad", "father"]):
                return self.get_random_dad_joke(lang)
            elif any(word in msg_lower for word in ["cat", "dog", "animal", "fish", "bird"]):
                return self.get_random_animal_joke()
            elif any(word in msg_lower for word in ["pun", "wordplay"]):
                return self.get_random_pun(lang)
            else:
                return self.get_random_joke(lang=lang)
