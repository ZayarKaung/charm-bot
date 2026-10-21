"""Sticker library — reply stickers chosen by emoji from admin-loaded packs."""

import logging
import random
import re

logger = logging.getLogger(__name__)

# Emoji that share a mood, so a reply asking for 🤣 can use a 😂 sticker.
MOOD_GROUPS = [
    "😂🤣😆😹😄😁😅😜😝🤪😺😸",
    "❤😍🥰😘💕💖💗💞💓😻💘💝🫶😚",
    "😢😭🥺😿😞😔💔",
    "😳☺😊🙈🥹🤭",
    "😡😠😤👿💢",
    "😮😲😱🤯😯",
    "👍👌✌🤝👏🙏💪",
    "😴🥱💤",
    "🤔🧐🤨",
    "😎🤩✨🔥",
    "👋🙋",
]
_GROUP_OF = {char: index for index, group in enumerate(MOOD_GROUPS) for char in group}

PACK_LINK = re.compile(r"(?:https?://)?t(?:elegram)?\.me/addstickers/([A-Za-z0-9_]+)")
PACK_NAME = re.compile(r"^[A-Za-z0-9_]+$")


def normalize_emoji(emoji: str) -> str:
    """Strip variation selectors and skin tones so similar emoji compare equal."""
    return re.sub("[️🏻-🏿]", "", emoji or "").strip()


def parse_pack_name(text: str) -> str | None:
    """Accept a t.me/addstickers link or a bare pack name."""
    text = (text or "").strip()
    match = PACK_LINK.search(text)
    if match:
        return match.group(1)
    return text if PACK_NAME.match(text) else None


async def fetch_sticker_pack(bot, name: str) -> list[tuple[str, str]]:
    """Download a pack's sticker list from Telegram as (file_id, emoji) pairs."""
    sticker_set = await bot.get_sticker_set(name)
    return [(sticker.file_id, sticker.emoji or "") for sticker in sticker_set.stickers]


class StickerLibrary:
    """In-memory index of reply stickers by emoji."""

    def __init__(self):
        self._by_emoji: dict[str, list[str]] = {}
        self._by_group: dict[int, list[str]] = {}

    def load(self, stickers: list[tuple[str, str]]) -> None:
        self._by_emoji, self._by_group = {}, {}
        for file_id, emoji in stickers:
            key = normalize_emoji(emoji)
            if not key:
                continue
            self._by_emoji.setdefault(key, []).append(file_id)
            group = _GROUP_OF.get(key[0])
            if group is not None:
                self._by_group.setdefault(group, []).append(file_id)

    def emojis(self) -> list[str]:
        """Emoji that have at least one sticker, for telling the AI what it can send."""
        return list(self._by_emoji)

    def __len__(self) -> int:
        return sum(len(ids) for ids in self._by_emoji.values())

    def pick(self, emoji: str | None) -> str | None:
        """Return a sticker file_id matching the emoji or its mood, if any."""
        key = normalize_emoji(emoji or "")
        if not key:
            return None
        candidates = self._by_emoji.get(key)
        if not candidates:
            group = _GROUP_OF.get(key[0])
            candidates = self._by_group.get(group) if group is not None else None
        return random.choice(candidates) if candidates else None
