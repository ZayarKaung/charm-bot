"""Offline regression checks: python -m unittest test_regressions -v"""
import asyncio
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

os.environ.setdefault('TELEGRAM_BOT_TOKEN', '123456:offline-test')

from models.database import Database
from utils.rate_limiter import check_rate_limit
from handlers.commands import button_callback, pickup_command
from handlers.messages import handle_message
from engine.jokes import JokesEngine
from engine.romance import RomanceEngine
from engine.ai_provider import (
    AIProvider,
    JOKES_BASE_PROMPT,
    build_system_prompt,
)
from handlers.commands import category_command
from engine.stickers import StickerLibrary
from utils.language import explicit_language, resolve_language


class BotTestBase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = Database(':memory:')
        await self.db.connect()
        self.user = SimpleNamespace(id=1, username='test', first_name='A_*[')
        await self.db.create_user(1, 'test', self.user.first_name)
        root = Path(__file__).resolve().parent
        self.context = SimpleNamespace(bot_data={
            'db': self.db, 'romance_engine': RomanceEngine(root / 'data'),
            'jokes_engine': JokesEngine(root / 'data'),
            'ai_provider': SimpleNamespace(is_available=lambda: True, generate_response=AsyncMock(return_value='reply')),
            'stickers': StickerLibrary(),
        })

    async def asyncTearDown(self):
        await self.db.close()


class BotRegressionTests(BotTestBase):

    async def test_daily_reset(self):
        await self.db._db.execute("UPDATE users SET daily_count=10, last_reset_date='2000-01-01'")
        await self.db._db.commit()
        self.assertEqual(await check_rate_limit(self.db, 1, 10), (True, 10))
        for _ in range(10):
            await self.db.increment_usage(1)
        self.assertEqual(await check_rate_limit(self.db, 1, 10), (False, 0))

    async def test_categories_preserve_underscores_and_language(self):
        engine = self.context.bot_data['jokes_engine']
        for category in engine.get_categories():
            for suffix, lang in [('', 'en'), ('_mm', 'mm')]:
                query = SimpleNamespace(from_user=self.user, data='cat_' + category + suffix,
                                        answer=AsyncMock(), edit_message_text=AsyncMock())
                with patch('handlers.commands.FREE_DAILY_LIMIT', 100), patch.object(engine, 'get_random_joke', return_value='safe') as get:
                    await button_callback(SimpleNamespace(callback_query=query), self.context)
                    get.assert_called_once_with(category=category, lang=lang)

    async def test_pickup_limit_and_usage(self):
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(effective_user=self.user, effective_chat=SimpleNamespace(id=100), message=message)
        with patch('handlers.commands.FREE_DAILY_LIMIT', 1):
            await pickup_command(update, self.context)
            self.assertEqual((await self.db.get_user(1))['daily_count'], 1)
            await pickup_command(update, self.context)
            self.assertIn('Daily Limit Reached', message.reply_text.call_args.args[0])
            self.assertEqual((await self.db.get_user(1))['daily_count'], 1)

    async def test_plain_text_and_failed_delivery_does_not_charge(self):
        message = SimpleNamespace(text='hello', reply_text=AsyncMock())
        update = SimpleNamespace(effective_user=self.user, effective_chat=SimpleNamespace(id=100), message=message)
        with patch.object(self.context.bot_data['ai_provider'], 'generate_response', AsyncMock(return_value='unmatched _ * [')):
            await handle_message(update, self.context)
            self.assertNotIn('parse_mode', message.reply_text.call_args.kwargs)
            self.assertEqual((await self.db.get_user(1))['daily_count'], 1)
            message.reply_text.side_effect = RuntimeError('delivery failed')
            with self.assertRaises(RuntimeError):
                await handle_message(update, self.context)
            self.assertEqual((await self.db.get_user(1))['daily_count'], 1)

    async def test_groq_runs_in_worker(self):
        provider = AIProvider(groq_api_key='offline')
        with patch('engine.ai_provider.asyncio.to_thread', AsyncMock(return_value='reply')) as worker:
            self.assertEqual(await provider.generate_romance_response('hello'), 'reply')
            self.assertEqual(await provider.generate_joke_response('hello'), 'reply')
            self.assertEqual(worker.await_count, 2)

    def test_resolve_language_precedence(self):
        # An explicit choice beats the message text.
        self.assertEqual(resolve_language('en', 'မင်္ဂလာပါ'), 'en')
        self.assertEqual(resolve_language('mm', 'hello there'), 'mm')
        # On auto, detect from the text.
        self.assertEqual(resolve_language('auto', 'မင်္ဂလာပါ'), 'mm')
        self.assertEqual(resolve_language('auto', 'hello there'), 'en')
        # No text: fall back to the Telegram client locale, then English.
        self.assertEqual(resolve_language('auto', None, 'my'), 'mm')
        self.assertEqual(resolve_language('auto', None, 'en-GB'), 'en')
        self.assertEqual(resolve_language('auto', None, None), 'en')
        # Only a real choice counts as explicit.
        self.assertIsNone(explicit_language('auto'))
        self.assertEqual(explicit_language('mm'), 'mm')

    def test_forced_language_directive_in_prompt(self):
        mirror = build_system_prompt(JOKES_BASE_PROMPT)
        forced_mm = build_system_prompt(JOKES_BASE_PROMPT, 'mm')
        forced_en = build_system_prompt(JOKES_BASE_PROMPT, 'en')
        self.assertIn('match the user', mirror)
        self.assertIn('entire response in Myanmar', forced_mm)
        self.assertIn('entire response in English', forced_en)
        # Every variant keeps the persona.
        for prompt in (mirror, forced_mm, forced_en):
            self.assertIn('Yoyo', prompt)

    async def test_explicit_preference_overrides_detected_language(self):
        """A user who picked English gets English even when writing Myanmar."""
        await self.db.update_user_language(1, 'en')
        engine = self.context.bot_data['jokes_engine']
        await self.db.update_user_mode(1, 'jokes')
        message = SimpleNamespace(text='မင်္ဂလာပါ', reply_text=AsyncMock())
        update = SimpleNamespace(effective_user=self.user, effective_chat=SimpleNamespace(id=100), message=message)
        with patch.object(self.context.bot_data['ai_provider'], 'generate_response', AsyncMock(return_value='joke')) as joke:
            await handle_message(update, self.context)
            self.assertEqual(joke.call_args.kwargs['lang'], 'en')

    async def test_auto_preference_follows_message_language(self):
        await self.db.update_user_language(1, 'auto')
        await self.db.update_user_mode(1, 'jokes')
        engine = self.context.bot_data['jokes_engine']
        message = SimpleNamespace(text='မင်္ဂလာပါ', reply_text=AsyncMock())
        update = SimpleNamespace(effective_user=self.user, effective_chat=SimpleNamespace(id=100), message=message)
        with patch.object(self.context.bot_data['ai_provider'], 'generate_response', AsyncMock(return_value='joke')) as joke:
            await handle_message(update, self.context)
            self.assertIsNone(joke.call_args.kwargs['lang'])
            self.assertEqual(joke.call_args.args[0], 'မင်္ဂလာပါ')

    async def test_ai_forced_only_when_user_chose(self):
        """forced_lang is passed to the AI only for an explicit preference."""
        await self.db.update_user_mode(1, 'jokes')
        provider = SimpleNamespace(
            is_available=lambda: True,
            generate_response=AsyncMock(return_value='ai joke'),
        )
        self.context.bot_data['ai_provider'] = provider
        message = SimpleNamespace(text='မင်္ဂလာပါ', reply_text=AsyncMock())
        update = SimpleNamespace(effective_user=self.user, effective_chat=SimpleNamespace(id=100), message=message)

        await self.db.update_user_language(1, 'auto')
        await handle_message(update, self.context)
        self.assertIsNone(provider.generate_response.call_args.kwargs['lang'])

        await self.db.update_user_language(1, 'mm')
        await handle_message(update, self.context)
        self.assertEqual(provider.generate_response.call_args.kwargs['lang'], 'mm')

    async def test_keyboards_emit_language_suffix(self):
        """Category and pickup buttons must carry the user's language."""
        for preference, expected in [('mm', 'mm'), ('en', 'en')]:
            await self.db.update_user_language(1, preference)
            message = SimpleNamespace(reply_text=AsyncMock())
            update = SimpleNamespace(effective_user=self.user, effective_chat=SimpleNamespace(id=100), message=message)

            with patch('handlers.commands.FREE_DAILY_LIMIT', 100):
                await category_command(update, self.context)
            markup = message.reply_text.call_args.kwargs['reply_markup']
            payloads = [b.callback_data for row in markup.inline_keyboard for b in row]
            self.assertTrue(payloads)
            for payload in payloads:
                self.assertTrue(payload.endswith('_' + expected), payload)

            message.reply_text.reset_mock()
            with patch('handlers.commands.FREE_DAILY_LIMIT', 100):
                await pickup_command(update, self.context)
            markup = message.reply_text.call_args.kwargs['reply_markup']
            payloads = [b.callback_data for row in markup.inline_keyboard for b in row]
            self.assertTrue(payloads)
            for payload in payloads:
                self.assertTrue(payload.endswith('_' + expected), payload)

    async def test_pickup_callback_roundtrip_preserves_language(self):
        """Every pickup payload the keyboard emits parses back correctly."""
        await self.db.update_user_language(1, 'mm')
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(effective_user=self.user, effective_chat=SimpleNamespace(id=100), message=message)
        with patch('handlers.commands.FREE_DAILY_LIMIT', 100):
            await pickup_command(update, self.context)
        markup = message.reply_text.call_args.kwargs['reply_markup']
        payloads = [b.callback_data for row in markup.inline_keyboard for b in row]

        engine = self.context.bot_data['romance_engine']
        for payload in payloads:
            expected_style = payload.removeprefix('pickup_').rsplit('_', 1)[0]
            query = SimpleNamespace(from_user=self.user, data=payload,
                                    answer=AsyncMock(), edit_message_text=AsyncMock())
            with patch('handlers.commands.FREE_DAILY_LIMIT', 100), \
                    patch.object(engine, 'get_random_pickup_line', return_value='safe') as get:
                await button_callback(SimpleNamespace(callback_query=query), self.context)
                get.assert_called_once_with(style=expected_style, lang='mm')

    async def test_gemini_failure_falls_back(self):
        provider = AIProvider(groq_api_key='offline')
        provider._gemini_model = Mock()
        model = SimpleNamespace(generate_content_async=AsyncMock(side_effect=TimeoutError()))
        with patch('engine.ai_provider.genai.GenerativeModel', return_value=model), patch(
            'engine.ai_provider.asyncio.to_thread', AsyncMock(return_value='fallback')
        ):
            self.assertEqual(await provider.generate_joke_response('hello'), 'fallback')
        options = model.generate_content_async.call_args.kwargs['request_options']
        self.assertEqual(options['timeout'], 12)
        self.assertIsNone(options['retry'])

    async def test_conversation_followup_receives_history(self):
        message = SimpleNamespace(text='My partner is May', reply_text=AsyncMock())
        update = SimpleNamespace(effective_user=self.user, effective_chat=SimpleNamespace(id=100), message=message)
        provider = self.context.bot_data['ai_provider']
        provider.generate_response.return_value = 'How is May?'
        await handle_message(update, self.context)
        message.text = 'Write her a greeting'
        await self.db.update_user_mode(1, 'lovely')
        await handle_message(update, self.context)
        kwargs = provider.generate_response.call_args.kwargs
        self.assertEqual(kwargs['mode'], 'lovely')
        self.assertEqual(kwargs['history'], [
            {'role': 'user', 'content': 'My partner is May'},
            {'role': 'assistant', 'content': 'How is May?'},
        ])

    async def test_memory_isolated_bounded_and_reset(self):
        from handlers.commands import reset_command
        for index in range(12):
            await self.db.save_conversation_turn(100, 1, str(index), 'reply')
        await self.db.save_conversation_turn(200, 1, 'other chat', 'reply')
        await self.db.save_conversation_turn(100, 2, 'other user', 'reply')
        history = await self.db.get_conversation(100, 1)
        self.assertEqual(len(history), 20)
        self.assertEqual(history[0]['content'], '2')
        update = SimpleNamespace(effective_chat=SimpleNamespace(id=100), effective_user=self.user,
                                 message=SimpleNamespace(reply_text=AsyncMock()))
        await reset_command(update, self.context)
        self.assertEqual(await self.db.get_conversation(100, 1), [])
        self.assertEqual((await self.db.get_conversation(200, 1))[0]['content'], 'other chat')
        self.assertEqual((await self.db.get_conversation(100, 2))[0]['content'], 'other user')

    async def test_unavailable_ai_does_not_fake_understanding_or_charge(self):
        provider = self.context.bot_data['ai_provider']
        provider.generate_response.return_value = None
        message = SimpleNamespace(text='Why did she say that?', reply_text=AsyncMock())
        update = SimpleNamespace(effective_user=self.user, effective_chat=SimpleNamespace(id=100), message=message)
        await handle_message(update, self.context)
        self.assertIn('temporarily unavailable', message.reply_text.call_args.args[0])
        self.assertEqual((await self.db.get_user(1))['daily_count'], 0)
        self.assertEqual(await self.db.get_conversation(100, 1), [])
        provider.is_available = lambda: False
        provider.generate_response.reset_mock()
        await handle_message(update, self.context)
        provider.generate_response.assert_not_awaited()
        self.assertEqual((await self.db.get_user(1))['daily_count'], 0)

    async def test_gemini_receives_roles_history_and_mode_instruction(self):
        provider = AIProvider()
        provider._gemini_model = Mock()
        model = SimpleNamespace(generate_content_async=AsyncMock(return_value=SimpleNamespace(text='Her name is May')))
        history = [{'role': 'user', 'content': 'My partner is May'}, {'role': 'assistant', 'content': 'Hello!'}]
        with patch('engine.ai_provider.genai.GenerativeModel', return_value=model) as factory:
            reply = await provider.generate_response('What is her name?', 'funny', lang='mm', history=history)
        self.assertEqual(reply, 'Her name is May')
        self.assertIn('Mode: Funny', factory.call_args.kwargs['system_instruction'])
        self.assertIn('entire response in Myanmar', factory.call_args.kwargs['system_instruction'])
        self.assertEqual(model.generate_content_async.call_args.args[0], [
            {'role': 'user', 'parts': ['My partner is May']},
            {'role': 'model', 'parts': ['Hello!']},
            {'role': 'user', 'parts': ['What is her name?']},
        ])

    async def test_groq_payload_keeps_conversation_roles(self):
        import json
        provider = AIProvider(groq_api_key='offline')
        response = Mock()
        response.status = 200
        response.read.return_value = b'{"choices":[{"message":{"content":"May"}}]}'
        manager = Mock()
        manager.__enter__ = Mock(return_value=response)
        manager.__exit__ = Mock(return_value=False)
        history = [{'role': 'user', 'content': 'May'}, {'role': 'assistant', 'content': 'Hello May'}]
        with patch('engine.ai_provider.urllib.request.urlopen', return_value=manager) as call:
            self.assertEqual(provider._call_groq_sync('system', 'Her name?', history), 'May')
        payload = json.loads(call.call_args.args[0].data)
        self.assertEqual(payload['messages'], [{'role': 'system', 'content': 'system'}, *history, {'role': 'user', 'content': 'Her name?'}])

    async def test_mode_buttons_switch_without_charging(self):
        from handlers.commands import get_persistent_keyboard
        from models.user import MODES
        labels = [button.text for row in get_persistent_keyboard().keyboard for button in row]
        for mode, label in MODES.items():
            self.assertIn(label, labels)
            message = SimpleNamespace(text=label, reply_text=AsyncMock())
            update = SimpleNamespace(effective_user=self.user, effective_chat=SimpleNamespace(id=100), message=message)
            await handle_message(update, self.context)
            self.assertEqual((await self.db.get_user(1))['mode'], mode)
        self.assertEqual((await self.db.get_user(1))['daily_count'], 0)

    async def test_startup_registers_modes_language_reset_and_fallback(self):
        import bot
        app = Mock()
        app.bot_data = {}
        app.bot = SimpleNamespace(set_my_commands=AsyncMock())
        with patch.object(bot, 'Database', return_value=self.db), patch.object(self.db, 'connect', AsyncMock()),                 patch.object(bot, 'STICKER_PACKS', []), patch.object(bot, 'AIProvider') as provider:
            await bot.post_init(app)
            provider.assert_called_once_with(bot.GEMINI_API_KEY, bot.GROQ_API_KEY)
        menu = [command.command for command in app.bot.set_my_commands.call_args.args[0]]
        with patch.object(bot.Application, 'builder') as builder:
            builder.return_value.token.return_value.post_init.return_value.post_shutdown.return_value.build.return_value = app
            with patch('builtins.print'):
                bot.main()
        registered = set().union(*(getattr(call.args[0], 'commands', set()) for call in app.add_handler.call_args_list))
        for command in ('chat', 'funny', 'lovely', 'settings', 'lang', 'reset', 'memory', 'forget', 'myid'):
            self.assertIn(command, registered)
            self.assertIn(command, menu)
        for command in ('jokes', 'romance', 'rename', 'addpack'):
            self.assertIn(command, registered)

    async def test_memory_survives_database_reopen(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'memory.db'
            db = Database(path)
            await db.connect()
            try:
                await db.save_conversation_turn(100, 1, 'My name is May', 'Hello May')
            finally:
                await db.close()
            reopened = Database(path)
            await reopened.connect()
            try:
                self.assertEqual((await reopened.get_conversation(100, 1))[0]['content'], 'My name is May')
            finally:
                await reopened.close()


class YoyoFeatureTests(BotTestBase):
    """Persona, onboarding, stickers, memory facts and Zawgyi handling."""

    def _update(self, text=None, **message_fields):
        message = SimpleNamespace(text=text, reply_text=AsyncMock(), reply_sticker=AsyncMock(), **message_fields)
        return SimpleNamespace(effective_user=self.user, effective_chat=SimpleNamespace(id=100), message=message)

    def test_parse_reply_strips_tags(self):
        from engine.ai_provider import parse_reply
        text, sticker, facts = parse_reply('Goodnight May 🌙\n[sticker: 😘]\n[remember: Partner is named May]')
        self.assertEqual((text, sticker, facts), ('Goodnight May 🌙', '😘', ['Partner is named May']))
        self.assertEqual(parse_reply('plain [not a tag]'), ('plain [not a tag]', None, []))
        # A tag cut off by the output limit is never shown.
        self.assertEqual(parse_reply('Rest well 🥺\n\n[sticker:'), ('Rest well 🥺', None, []))

    async def test_gemini_overload_is_retried_once(self):
        provider = AIProvider()
        provider._gemini_model = Mock()
        overloaded = type('ServiceUnavailable', (Exception,), {})
        model = SimpleNamespace(generate_content_async=AsyncMock(
            side_effect=[overloaded('503'), SimpleNamespace(text='hello again')]))
        with patch('engine.ai_provider.genai.GenerativeModel', return_value=model), \
                patch('engine.ai_provider.asyncio.sleep', AsyncMock()):
            self.assertEqual(await provider.generate_response('hi'), 'hello again')
        self.assertEqual(model.generate_content_async.await_count, 2)

    def test_persona_prompt_uses_name_gender_nickname_and_facts(self):
        from engine.ai_provider import build_persona_prompt
        prompt = build_persona_prompt('lovely', {
            'bot_name': 'Mimi', 'bot_gender': 'male', 'nickname': 'ကိုကို', 'facts': ['Likes coffee'],
            'sticker_emoji': ['😎', '😳'],
        }, 'A')
        for expected in ('You are Mimi', 'Mode: Lovely', 'ကျွန်တော်', '"ကိုကို"', 'Likes coffee', 'one of these emoji: 😎 😳'):
            self.assertIn(expected, prompt)
        # Without reply stickers loaded, the AI is not told to send any.
        neutral = build_persona_prompt('chat')
        self.assertIn('gender-neutral', neutral)
        self.assertNotIn('[sticker:', neutral)

    def test_legacy_modes_map_to_new_modes(self):
        from models.user import normalize_mode
        self.assertEqual([normalize_mode(m) for m in ('jokes', 'romance', 'flirt', None, 'funny')],
                         ['funny', 'lovely', 'chat', 'chat', 'funny'])

    async def test_reply_sticker_memory_facts_and_history(self):
        self.context.bot_data['stickers'].load([('sticker-love', '❤️')])
        provider = self.context.bot_data['ai_provider']
        provider.generate_response.return_value = 'Aww 💕\n[sticker: 😍]\n[remember: Partner is named May]'
        update = self._update("My partner's name is May")
        await handle_message(update, self.context)
        update.message.reply_text.assert_awaited_once_with('Aww 💕')
        update.message.reply_sticker.assert_awaited_once_with('sticker-love')
        self.assertEqual(await self.db.get_facts(100, 1), ['Partner is named May'])
        self.assertEqual((await self.db.get_conversation(100, 1))[1]['content'], 'Aww 💕\n[sticker: 😍]')
        self.assertEqual((await self.db.get_user(1))['daily_count'], 1)
        # The next turn sends the remembered fact to the AI.
        await handle_message(self._update('Write her a note'), self.context)
        self.assertEqual(provider.generate_response.call_args.kwargs['persona']['facts'], ['Partner is named May'])

    async def test_onboarding_gender_then_nickname(self):
        message = SimpleNamespace(reply_text=AsyncMock())
        for data in ('gender_female_o', 'nick_p0_o'):
            query = SimpleNamespace(from_user=self.user, data=data, message=message,
                                    answer=AsyncMock(), edit_message_text=AsyncMock())
            await button_callback(SimpleNamespace(callback_query=query), self.context)
        user = await self.db.get_user(1)
        self.assertEqual((user['bot_gender'], user['nickname']), ('female', 'ကိုကို'))
        # After the nickname, the user is asked to pick a mode.
        markup = message.reply_text.call_args.kwargs['reply_markup']
        self.assertEqual([b.callback_data for b in markup.inline_keyboard[0]], ['mode_chat', 'mode_funny', 'mode_lovely'])

    async def test_typed_nickname_is_saved_not_sent_to_ai(self):
        query = SimpleNamespace(from_user=self.user, data='nick_custom_s', message=SimpleNamespace(reply_text=AsyncMock()),
                                answer=AsyncMock(), edit_message_text=AsyncMock())
        await button_callback(SimpleNamespace(callback_query=query), self.context)
        await handle_message(self._update('Honey'), self.context)
        user = await self.db.get_user(1)
        self.assertEqual((user['nickname'], user['pending_input'], user['daily_count']), ('Honey', None, 0))
        self.context.bot_data['ai_provider'].generate_response.assert_not_awaited()

    async def test_sticker_is_described_and_image_passed_to_ai(self):
        from handlers.messages import handle_media
        webp = b'RIFF\x00\x00\x00\x00WEBPVP8 '
        telegram_file = SimpleNamespace(download_as_bytearray=AsyncMock(return_value=bytearray(webp)))
        self.context.bot = SimpleNamespace(get_file=AsyncMock(return_value=telegram_file), send_chat_action=AsyncMock())
        sticker = SimpleNamespace(emoji='😂', set_name='nkosip_mini', is_animated=False, is_video=False,
                                  file_id='file-1', thumbnail=None)
        update = self._update(sticker=sticker, photo=None, caption=None)
        await handle_media(update, self.context)
        call = self.context.bot_data['ai_provider'].generate_response.call_args
        self.assertEqual(call.args[0], '[The user sent a sticker: 😂 from pack "nkosip_mini"]')
        self.assertEqual(call.kwargs['image'], (webp, 'image/webp'))
        self.assertEqual((await self.db.get_user(1))['daily_count'], 1)

    async def test_zawgyi_input_is_converted_before_ai(self):
        await handle_message(self._update('ေနေကာင္းလား'), self.context)
        self.assertEqual(self.context.bot_data['ai_provider'].generate_response.call_args.args[0], 'နေကောင်းလား')

    async def test_addpack_is_admin_only(self):
        from handlers.commands import addpack_command
        update = self._update()
        self.context.args = ['https://t.me/addstickers/nkosip_mini']
        self.context.bot = SimpleNamespace(get_sticker_set=AsyncMock(return_value=SimpleNamespace(
            stickers=[SimpleNamespace(file_id='s1', emoji='😂')])))
        with patch('handlers.commands.ADMIN_USER_ID', 999):
            await addpack_command(update, self.context)
        self.context.bot.get_sticker_set.assert_not_awaited()
        with patch('handlers.commands.ADMIN_USER_ID', 1):
            await addpack_command(update, self.context)
        self.context.bot.get_sticker_set.assert_awaited_once_with('nkosip_mini')
        self.assertEqual(self.context.bot_data['stickers'].pick('😂'), 's1')

    async def test_forget_clears_facts_and_conversation(self):
        from handlers.commands import forget_command
        await self.db.add_facts(100, 1, ['Likes tea'])
        await self.db.save_conversation_turn(100, 1, 'hi', 'hello')
        await forget_command(self._update(), self.context)
        self.assertEqual((await self.db.get_facts(100, 1), await self.db.get_conversation(100, 1)), ([], []))


if __name__ == '__main__':
    unittest.main()

