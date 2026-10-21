# Charm Bot — Yoyo 🤖

A Telegram AI companion named **Yoyo** that chats naturally in **Myanmar (Burmese) and English**.
Pick a mode and talk to it like a friend: it understands what you say, remembers context,
and reads emoji, stickers and photos.

မြန်မာ နဲ့ English နှစ်မျိုးလုံး သဘာဝကျကျ စကားပြောနိုင်တဲ့ Telegram AI သူငယ်ချင်း **Yoyo** ပါ။

## Features

- **Modes** — 💬 Chat (friendly), 😂 Funny (jokes and banter), 💕 Lovely (sweet and romantic).
  The mode changes Yoyo's tone, not its intelligence.
- **Your own Yoyo** — on `/start`, choose Yoyo's gender (neutral, male or female) and what Yoyo
  calls you. Male/female changes the Burmese wording (ကျွန်တော်/ခင်ဗျာ, ကျွန်မ/ရှင်). Rename Yoyo anytime.
- **Memory** — remembers the last 10 exchanges and lasting facts you share (names, likes, dates).
- **Emoji, stickers and photos** — understands what you send, and sometimes replies with a sticker.
- **Myanmar support** — auto-detects language, converts Zawgyi to Unicode, understands romanized Burmese.
- **Extras** — curated pickup lines (`/pickup`) and jokes by category (`/category`).
- **Daily free limit** — failed replies don't count against it.

## AI providers

1. **Google Gemini** (main) — best Burmese quality; can see stickers and photos.
2. **Second Gemini model** — used when the main one is overloaded.
3. **Groq** (last resort) — fast, but its Burmese is noticeably weaker.

The free Gemini tier has a small daily quota. For real users, enable billing for your Gemini
API key in [Google AI Studio](https://aistudio.google.com).

## Setup

Requires **Python 3.10+** (developed on 3.13).

1. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and fill in your own values:

   | Setting | Where to get it |
   |---|---|
   | `TELEGRAM_BOT_TOKEN` (required) | Message [@BotFather](https://t.me/BotFather) → `/newbot` |
   | `GEMINI_API_KEY` | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) |
   | `GROQ_API_KEY` | [console.groq.com/keys](https://console.groq.com/keys) |
   | `ADMIN_USER_ID` | Start the bot and send it `/myid` |
   | `STICKER_PACKS` | Pack names from `t.me/addstickers/<name>`, comma-separated |

   At least one AI key is needed for conversation. **Never share or commit `.env`.**

3. Start the bot:

   ```bash
   python bot.py
   ```

4. In Telegram, send `/start` to your bot.

## Commands

| Command | What it does |
|---|---|
| `/start` | Welcome and set up Yoyo's gender and your nickname |
| `/chat`, `/funny`, `/lovely` | Switch mode |
| `/settings` | Change Yoyo's gender, your nickname, Yoyo's name, language |
| `/rename <name>` | Give Yoyo a new name |
| `/lang` | Language: Auto, English or Myanmar |
| `/reset` | Clear recent conversation |
| `/memory` | Show what Yoyo remembers about you |
| `/forget` | Erase everything Yoyo remembers |
| `/pickup`, `/category` | Pickup lines and jokes |
| `/profile`, `/premium` | Your usage and plans (payments not available yet) |
| `/myid` | Show your Telegram user ID |
| `/addpack <link>` | Admin only: add a sticker pack for replies |
| `/help` | All commands |

## Project structure

```
bot.py               Startup, handler and command registration
config.py            Settings from .env
engine/              AI providers and persona prompts, stickers, curated content
handlers/            Commands, messages/stickers/photos, payments placeholder
models/              SQLite database and user/mode constants
utils/               Language detection, Zawgyi, rate limiting, message texts
data/                Curated romance, pickup and joke content (EN + MM)
test_regressions.py  Offline tests
make_zip.py          Build a shareable zip without secrets
```

## Tests

```bash
python -B -m unittest test_regressions -v
```

The tests run offline with mocked AI and Telegram; they don't use your API keys.

## Sharing the project

```bash
python make_zip.py
```

This writes `dist/charm-bot-<date>.zip` containing only committed files. `.env`, databases and
caches are always left out, and the script refuses to build a zip that contains them.

## Not implemented yet

- Payments and Premium (the Premium screen says so)
- Spicy/18+ mode
