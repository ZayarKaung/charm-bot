"""AI Provider module — Yoyo persona prompts with Google Gemini & Groq fallback."""

import asyncio
import os
import json
import logging
import re
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

# Gemini API check
try:
    import google.generativeai as genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False
    logger.warning("google-generativeai not installed. Gemini features disabled.")


CONVERSATION_PROMPT = (
    "You are {bot_name}, an AI companion chatting with one person on Telegram. "
    "Talk like a real friend in a natural back-and-forth, not like an assistant reading a script. "
    "Understand and answer the user's actual message first. Use the conversation history and "
    "the facts you remember to resolve follow-ups, names and references. "
    "You have broad general knowledge: answer real questions properly in every mode. "
    "A mode changes your tone, never your intelligence. "
    "If the user corrects you, acknowledge it and adapt. Ask at most one short question back. "
    "Do not respond with unrelated quotes, canned pickup lines or random jokes. "
    "You are an AI and say so honestly if asked; do not invent a human life, real-world actions "
    "or meetings. Keep replies short like chat messages (1-4 sentences) unless the user asks "
    "for something longer, such as a poem or letter. Plain text only, no Markdown. "
    "Emoji are part of the conversation: read them as tone (for example 😭 can mean crying "
    "with laughter, 🙂 can be cold or polite) and use a few emoji naturally yourself. "
    "Messages in [square brackets] describe a sticker or photo the user sent; react to what it "
    "shows and the feeling behind it, as a friend would. "
    "Users may write Burmese in Myanmar script, in Zawgyi-style spelling, in romanized Burmese "
    "(for example 'nay kaung lar') or mixed with English: understand all of them. "
)
MODE_PROMPTS = {
    "chat": "Mode: Chat. Be friendly, warm, thoughtful and helpful, like a close friend. ",
    "funny": (
        "Mode: Funny. Be witty, playful and teasing. Find the humour in what the user actually "
        "said, use light banter and wordplay, and tell jokes when asked. Still answer real "
        "questions, and drop the jokes if the user is upset or in distress. "
    ),
    "lovely": (
        "Mode: Lovely. Be warm, caring, sweet and romantic. Notice the user's feelings, comfort "
        "them, compliment them sincerely and write romantic messages on request. Stay tender "
        "and respectful; never sexual or explicit. "
    ),
}
GENDER_PROMPTS = {
    "neutral": (
        "Your identity: you are a gender-neutral AI. In Burmese avoid gendered self-words and "
        "particles (use casual forms such as ငါ/ကိုယ် or just drop the pronoun, and neutral "
        "endings like နော်/ပါ). "
    ),
    "male": (
        "Your identity: you present as male. In Burmese refer to yourself as ကျွန်တော် (or "
        "ကိုယ်/ငါ when very casual) and use male polite endings such as ခင်ဗျာ/ဗျ. "
    ),
    "female": (
        "Your identity: you present as female. In Burmese refer to yourself as ကျွန်မ (or "
        "ကိုယ်/ငါ when very casual) and use female polite endings such as ရှင်/နော်. "
    ),
}
# The model may end a reply with these optional tags; parse_reply() strips them.
TAG_INSTRUCTIONS = (
    "Optional tags, each on its own line at the very end of your reply and never explained: "
    "[remember: <short fact>] when the user shares a lasting personal fact worth remembering "
    "(their name, partner's name, likes, important dates, job). Write facts in English. "
)
STICKER_INSTRUCTIONS = (
    "[sticker: <emoji>] to also send a sticker, in roughly one of every four replies when the "
    "mood fits. Use only one of these emoji: {emoji}. "
)
ROMANCE_BASE_PROMPT = CONVERSATION_PROMPT.format(bot_name="Yoyo") + MODE_PROMPTS["lovely"]
JOKES_BASE_PROMPT = CONVERSATION_PROMPT.format(bot_name="Yoyo") + MODE_PROMPTS["funny"]

TAG_PATTERN = re.compile(r"\[(sticker|remember)\s*:\s*([^\]\n]*)\]", re.IGNORECASE)
UNCLOSED_TAG = re.compile(r"\[(?:sticker|remember)\b[^\]]*$", re.IGNORECASE)


def parse_reply(text: str) -> tuple[str, str | None, list[str]]:
    """Split a model reply into (visible text, sticker emoji, facts to remember)."""
    sticker, facts = None, []
    for kind, value in TAG_PATTERN.findall(text):
        value = value.strip()
        if not value:
            continue
        if kind.lower() == "sticker":
            sticker = sticker or value
        else:
            facts.append(value)
    clean = TAG_PATTERN.sub("", text)
    # Drop a tag cut off by the output limit, such as a trailing "[sticker:".
    clean = UNCLOSED_TAG.sub("", clean)
    clean = re.sub(r"\n{3,}", "\n\n", clean).strip()
    return clean, sticker, facts


def build_persona_prompt(mode: str, persona: dict | None = None, user_name: str = "") -> str:
    """Base prompt for one turn: identity, mode, how to address the user, memory, tags."""
    persona = persona or {}
    bot_name = persona.get("bot_name") or "Yoyo"
    prompt = CONVERSATION_PROMPT.format(bot_name=bot_name)
    prompt += MODE_PROMPTS.get(mode, MODE_PROMPTS["chat"])
    prompt += GENDER_PROMPTS.get(persona.get("bot_gender") or "neutral", GENDER_PROMPTS["neutral"])
    nickname = persona.get("nickname")
    if nickname:
        prompt += "Call the user " + json.dumps(nickname, ensure_ascii=False) + " when addressing them. "
    elif user_name:
        prompt += "The user's display name is " + json.dumps(user_name, ensure_ascii=False) + ". "
    facts = persona.get("facts") or []
    if facts:
        prompt += "Facts you remember about the user: " + "; ".join(facts) + ". "
    prompt += TAG_INSTRUCTIONS
    sticker_emoji = persona.get("sticker_emoji") or []
    if sticker_emoji:
        prompt += STICKER_INSTRUCTIONS.format(emoji=" ".join(sticker_emoji))
    return prompt

# Used when the user has no explicit language preference (auto-detect).
MIRROR_LANGUAGE_DIRECTIVE = (
    "IMPORTANT: If the user writes in Myanmar (Burmese), you MUST respond in Myanmar. "
    "If the user writes in English, respond in English. "
    "Always match the user's language."
)

# Used when the user has explicitly chosen a language via /lang.
FORCED_LANGUAGE_DIRECTIVES = {
    "mm": (
        "IMPORTANT: You MUST write your entire response in Myanmar (Burmese), "
        "using Myanmar script. Do this even if the user writes in English or "
        "another language. Never reply in English."
    ),
    "en": (
        "IMPORTANT: You MUST write your entire response in English. "
        "Do this even if the user writes in Myanmar (Burmese) or another language. "
        "Never reply in Myanmar."
    ),
}


def build_system_prompt(base_prompt: str, lang: str | None = None) -> str:
    """Attach the right language directive to a base persona prompt."""
    directive = FORCED_LANGUAGE_DIRECTIVES.get(lang or "", MIRROR_LANGUAGE_DIRECTIVE)
    return base_prompt + directive


# Backwards-compatible defaults (auto-detect / mirror behaviour).
ROMANCE_SYSTEM_PROMPT = build_system_prompt(ROMANCE_BASE_PROMPT)
JOKES_SYSTEM_PROMPT = build_system_prompt(JOKES_BASE_PROMPT)


class AIProvider:
    """Multi-provider AI integration with Gemini and Groq fallback."""

    def __init__(self, gemini_api_key: str | None = None, groq_api_key: str | None = None):
        self._gemini_api_key = gemini_api_key
        self._groq_api_key = groq_api_key
        self._gemini_model = None
        self._model_name = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
        # Tried when the main model is overloaded or unavailable (empty to disable).
        self._fallback_model_name = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.5-flash")

        if gemini_api_key and GENAI_AVAILABLE:
            try:
                genai.configure(api_key=gemini_api_key)
                self._gemini_model = genai.GenerativeModel(self._model_name)
                logger.info("✅ Gemini AI initialized successfully")
            except Exception as e:
                logger.error("❌ Failed to initialize Gemini AI: %s", e)
                self._gemini_model = None

        if self._groq_api_key:
            logger.info("✅ Groq AI fallback initialized successfully")

    def is_available(self) -> bool:
        """Check if at least one AI provider is available."""
        return self._gemini_model is not None or bool(self._groq_api_key)

    def _call_groq_sync(self, system_prompt: str, user_prompt: str, history: list[dict] | None = None) -> str | None:
        """Synchronous HTTP call to Groq's OpenAI-compatible chat completion endpoint."""
        if not self._groq_api_key:
            return None

        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._groq_api_key}",
            "Content-Type": "application/json",
            "User-Agent": "CharmBot/1.0",
        }
        payload = {
            # llama-3.3-70b-versatile was retired by Groq (404); override via GROQ_MODEL.
            "model": os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
            "messages": [
                {"role": "system", "content": system_prompt},
                *(history or []),
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": 800,
            "temperature": 0.85,
        }

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=12) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode("utf-8"))
                    return data["choices"][0]["message"]["content"].strip()
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:300].replace(self._groq_api_key, "[redacted]")
            logger.error("Groq API HTTP %s for model %s: %s", e.code, payload["model"], body)
        except Exception as e:
            logger.error("Groq API request error: %s", e)
        return None

    async def generate_response(
        self, user_message: str, mode: str = "chat", user_name: str = "",
        lang: str | None = None, history: list[dict] | None = None,
        persona: dict | None = None, image: tuple[bytes, str] | None = None,
    ) -> str | None:
        """Generate one conversational turn, retaining roles across both providers.

        image is an optional (bytes, mime_type) pair, such as a sticker or photo;
        only Gemini can see it, so user_message should also describe it in text.
        """
        system_prompt = build_system_prompt(build_persona_prompt(mode, persona, user_name), lang)
        history = (history or [])[-20:]
        # Gemini writes much better Burmese than Groq, so when the main model is
        # overloaded or unavailable, try the second Gemini model before Groq.
        model_names = [self._model_name]
        if self._fallback_model_name and self._fallback_model_name != self._model_name:
            model_names.append(self._fallback_model_name)
        for attempt, model_name in enumerate(model_names if self._gemini_model is not None else []):
            try:
                model = genai.GenerativeModel(model_name, system_instruction=system_prompt)
                contents = [
                    {"role": "model" if turn["role"] == "assistant" else "user",
                     "parts": [turn["content"]]}
                    for turn in history
                ]
                parts = [user_message]
                if image:
                    parts.append({"mime_type": image[1], "data": image[0]})
                contents.append({"role": "user", "parts": parts})
                response = await asyncio.wait_for(
                    model.generate_content_async(
                        contents,
                        request_options={"timeout": 12, "retry": None},
                        # Burmese text and the model's thinking both use many tokens.
                        generation_config=genai.types.GenerationConfig(
                            max_output_tokens=2048, temperature=0.8,
                        ),
                    ), timeout=15,
                )
                if response and response.text and response.text.strip():
                    return response.text.strip()
                break
            except Exception as error:
                detail = str(error).replace(self._gemini_api_key or "[no-key]", "[redacted]")
                logger.warning("Gemini %s failed (%s): %s; trying fallback", model_name, type(error).__name__, detail)
                # A timeout already used the time budget; don't wait on a second model.
                if isinstance(error, (TimeoutError, asyncio.TimeoutError)):
                    break
        if self._groq_api_key:
            return await asyncio.to_thread(
                self._call_groq_sync, system_prompt, user_message, history
            )
        return None

    async def generate_romance_response(self, user_message: str, user_name: str = "", lang: str | None = None) -> str | None:
        return await self.generate_response(user_message, "lovely", user_name, lang)

    async def generate_joke_response(self, user_message: str, lang: str | None = None) -> str | None:
        return await self.generate_response(user_message, "funny", lang=lang)
