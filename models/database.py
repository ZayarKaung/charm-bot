"""Database module for Charm Bot — async SQLite via aiosqlite."""

import logging
from datetime import date

import aiosqlite

logger = logging.getLogger(__name__)


class Database:
    """Async SQLite database manager for user data and tracking."""

    def __init__(self, db_path: str):
        self.db_path = str(db_path)
        self._db: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        """Open the database connection and create tables."""
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        await self._create_tables()
        logger.info("✅ Database connected: %s", self.db_path)

    async def close(self) -> None:
        """Close the database connection."""
        if self._db:
            await self._db.close()
            logger.info("Database connection closed.")

    async def _create_tables(self) -> None:
        """Create the required tables if they don't exist."""
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                mode TEXT DEFAULT 'chat',
                language_preference TEXT DEFAULT 'auto',
                is_premium INTEGER DEFAULT 0,
                daily_count INTEGER DEFAULT 0,
                last_reset_date TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await self._db.commit()
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS conversation_turns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                user_text TEXT NOT NULL,
                assistant_text TEXT NOT NULL
            )
        """)
        await self._db.execute("CREATE INDEX IF NOT EXISTS conversation_scope ON conversation_turns(chat_id, user_id, id)")
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS user_facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                fact TEXT NOT NULL,
                UNIQUE(chat_id, user_id, fact)
            )
        """)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS stickers (
                file_id TEXT PRIMARY KEY,
                emoji TEXT NOT NULL,
                pack TEXT NOT NULL
            )
        """)
        await self._db.commit()
        # Migrate: add columns missing from older databases
        await self._migrate_add_column("users", "language_preference", "TEXT DEFAULT 'auto'")
        await self._migrate_add_column("users", "bot_name", "TEXT DEFAULT 'Yoyo'")
        await self._migrate_add_column("users", "bot_gender", "TEXT DEFAULT 'neutral'")
        await self._migrate_add_column("users", "nickname", "TEXT")
        await self._migrate_add_column("users", "pending_input", "TEXT")

    async def _migrate_add_column(self, table: str, column: str, col_type: str) -> None:
        """Add a column if it doesn't already exist (safe migration)."""
        try:
            async with self._db.execute(f"PRAGMA table_info({table})") as cursor:
                columns = [row[1] for row in await cursor.fetchall()]
            if column not in columns:
                await self._db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
                await self._db.commit()
                logger.info("🔄 Migrated: added column '%s' to '%s'", column, table)
        except Exception as e:
            logger.warning("Migration check for %s.%s failed: %s", table, column, e)

    async def get_user(self, user_id: int) -> dict | None:
        """Retrieve a user by their Telegram user ID."""
        async with self._db.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
        return None

    async def create_user(self, user_id: int, username: str, first_name: str) -> dict:
        """Create a new user record."""
        today = date.today().isoformat()
        await self._db.execute(
            """INSERT OR IGNORE INTO users 
               (user_id, username, first_name, mode, is_premium, daily_count, last_reset_date)
               VALUES (?, ?, ?, 'chat', 0, 0, ?)""",
            (user_id, username, first_name, today),
        )
        await self._db.commit()
        return await self.get_user(user_id)

    async def get_or_create_user(self, user_id: int, username: str, first_name: str) -> dict:
        """Get existing user or create a new one."""
        user = await self.get_user(user_id)
        if user is None:
            user = await self.create_user(user_id, username, first_name)
        return user

    async def update_user_mode(self, user_id: int, mode: str) -> None:
        """Update the user's current chat mode."""
        await self._db.execute(
            "UPDATE users SET mode = ? WHERE user_id = ?", (mode, user_id)
        )
        await self._db.commit()

    async def update_user_language(self, user_id: int, language: str) -> None:
        """Update the user's language preference ('auto', 'en', or 'mm')."""
        await self._db.execute(
            "UPDATE users SET language_preference = ? WHERE user_id = ?", (language, user_id)
        )
        await self._db.commit()

    async def increment_usage(self, user_id: int) -> int:
        """Increment daily usage count and return the new count."""
        await self.reset_usage_if_needed(user_id)
        await self._db.execute(
            "UPDATE users SET daily_count = daily_count + 1 WHERE user_id = ?",
            (user_id,),
        )
        await self._db.commit()
        user = await self.get_user(user_id)
        return user["daily_count"]

    async def reset_usage_if_needed(self, user_id: int) -> None:
        """Reset daily count if the date has changed."""
        user = await self.get_user(user_id)
        if user is None:
            return

        today = date.today().isoformat()
        if user["last_reset_date"] != today:
            await self._db.execute(
                "UPDATE users SET daily_count = 0, last_reset_date = ? WHERE user_id = ?",
                (today, user_id),
            )
            await self._db.commit()

    async def get_user_count(self) -> int:
        """Get total number of registered users."""
        async with self._db.execute("SELECT COUNT(*) FROM users") as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

    async def get_conversation(self, chat_id: int, user_id: int) -> list[dict]:
        """Recent turns, isolated by Telegram chat and user, in chronological order."""
        async with self._db.execute(
            "SELECT user_text, assistant_text FROM conversation_turns WHERE chat_id=? AND user_id=? ORDER BY id DESC LIMIT 10",
            (chat_id, user_id),
        ) as cursor:
            rows = await cursor.fetchall()
        return [message for row in reversed(rows) for message in (
            {"role": "user", "content": row["user_text"]},
            {"role": "assistant", "content": row["assistant_text"]},
        )]

    async def save_conversation_turn(self, chat_id: int, user_id: int, user_text: str, assistant_text: str) -> None:
        """Store delivered turns; retain at most ten exchanges per conversation."""
        await self._db.execute(
            "INSERT INTO conversation_turns(chat_id,user_id,user_text,assistant_text) VALUES(?,?,?,?)",
            (chat_id, user_id, user_text, assistant_text),
        )
        await self._db.execute(
            "DELETE FROM conversation_turns WHERE chat_id=? AND user_id=? AND id NOT IN "
            "(SELECT id FROM conversation_turns WHERE chat_id=? AND user_id=? ORDER BY id DESC LIMIT 10)",
            (chat_id, user_id, chat_id, user_id),
        )
        await self._db.commit()

    async def clear_conversation(self, chat_id: int, user_id: int) -> None:
        await self._db.execute("DELETE FROM conversation_turns WHERE chat_id=? AND user_id=?", (chat_id, user_id))
        await self._db.commit()

    # --- Persona settings ---

    async def update_user_field(self, user_id: int, field: str, value) -> None:
        """Update one persona/setting column for a user."""
        if field not in ("bot_name", "bot_gender", "nickname", "pending_input"):
            raise ValueError(f"Unsupported user field: {field}")
        await self._db.execute(f"UPDATE users SET {field} = ? WHERE user_id = ?", (value, user_id))
        await self._db.commit()

    # --- Long-term facts ---

    MAX_FACTS = 30

    async def get_facts(self, chat_id: int, user_id: int) -> list[str]:
        async with self._db.execute(
            "SELECT fact FROM user_facts WHERE chat_id=? AND user_id=? ORDER BY id", (chat_id, user_id)
        ) as cursor:
            return [row["fact"] for row in await cursor.fetchall()]

    async def add_facts(self, chat_id: int, user_id: int, facts: list[str]) -> None:
        """Store new facts, ignoring duplicates and keeping only the newest MAX_FACTS."""
        for fact in facts:
            await self._db.execute(
                "INSERT OR IGNORE INTO user_facts(chat_id,user_id,fact) VALUES(?,?,?)",
                (chat_id, user_id, fact[:200]),
            )
        await self._db.execute(
            "DELETE FROM user_facts WHERE chat_id=? AND user_id=? AND id NOT IN "
            "(SELECT id FROM user_facts WHERE chat_id=? AND user_id=? ORDER BY id DESC LIMIT ?)",
            (chat_id, user_id, chat_id, user_id, self.MAX_FACTS),
        )
        await self._db.commit()

    async def clear_facts(self, chat_id: int, user_id: int) -> None:
        await self._db.execute("DELETE FROM user_facts WHERE chat_id=? AND user_id=?", (chat_id, user_id))
        await self._db.commit()

    # --- Stickers ---

    async def save_stickers(self, pack: str, stickers: list[tuple[str, str]]) -> None:
        """Replace a pack's stickers with (file_id, emoji) pairs."""
        await self._db.execute("DELETE FROM stickers WHERE pack=?", (pack,))
        await self._db.executemany(
            "INSERT OR REPLACE INTO stickers(file_id,emoji,pack) VALUES(?,?,?)",
            [(file_id, emoji, pack) for file_id, emoji in stickers],
        )
        await self._db.commit()

    async def get_stickers(self) -> list[tuple[str, str]]:
        async with self._db.execute("SELECT file_id, emoji FROM stickers") as cursor:
            return [(row["file_id"], row["emoji"]) for row in await cursor.fetchall()]

    async def get_sticker_packs(self) -> list[str]:
        async with self._db.execute("SELECT DISTINCT pack FROM stickers ORDER BY pack") as cursor:
            return [row["pack"] for row in await cursor.fetchall()]
