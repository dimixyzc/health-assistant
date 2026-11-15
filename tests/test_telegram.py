import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiogram.exceptions import TelegramBadRequest
from bot.delivery import ReplyMiddleware, answer, progress, send_text, chunks, telegram_html
from bot.handlers import commands
from bot import scheduler
from analytics import formatter


def message(text='/test', chat_id=1):
    pending = SimpleNamespace(edit_text=AsyncMock())
    return SimpleNamespace(text=text, chat=SimpleNamespace(id=chat_id),
                           answer=AsyncMock(return_value=pending)), pending


class TelegramTest(unittest.IsolatedAsyncioTestCase):
    async def test_progress_is_replaced_by_final_answer(self):
        event, pending = message()
        async def handler(event, data):
            await progress(event, 'Loading')
            await answer(event, '**Done** & safe')
        await ReplyMiddleware(1)(handler, event, {})
        self.assertEqual(event.answer.await_count, 1)
        pending.edit_text.assert_awaited_once_with('<b>Done</b> &amp; safe', parse_mode='HTML')

    async def test_uneditable_placeholder_falls_back_to_new_message(self):
        send = AsyncMock()
        edit = AsyncMock(side_effect=TelegramBadRequest(method='editMessageText', message='message to edit not found'))
        await send_text(send, '*Done*', edit=edit)
        send.assert_awaited_once_with('<b>Done</b>', parse_mode='HTML')

    async def test_long_emoji_text_is_delivered_in_safe_chunks(self):
        send = AsyncMock()
        text = '🧠' * 5000
        await send_text(send, text)
        parts = [call.args[0] for call in send.await_args_list]
        self.assertEqual(''.join(parts), text)
        self.assertTrue(all(len(p.encode('utf-16-le')) // 2 <= 4096 for p in parts))

    async def test_handler_exception_and_timeout_deliver_reply(self):
        async def broken(event, data):
            await progress(event, 'Loading')
            raise ValueError('private test detail')
        async def stalled(event, data):
            await progress(event, 'Loading')
            await asyncio.sleep(10)
        for handler in (broken, stalled):
            event, pending = message()
            await ReplyMiddleware(1, timeout=0.01)(handler, event, {})
            pending.edit_text.assert_awaited_once()
            self.assertNotIn('private test detail', str(pending.edit_text.call_args))

    async def test_unauthorized_chat_is_ignored(self):
        event, _ = message(chat_id=2)
        handler = AsyncMock()
        await ReplyMiddleware(1)(handler, event, {})
        handler.assert_not_awaited()
        event.answer.assert_not_awaited()

    async def test_experiment_without_payload_returns_usage(self):
        event, _ = message('/experiment_start')
        with patch.object(commands.settings, 'telegram_chat_id', 1):
            await commands.cmd_experiment_start(event)
        self.assertIn('experiment_start', event.answer.call_args.args[0])

    async def test_unknown_command_and_voice_get_explanation(self):
        for text in ('/unknown', None):
            event, _ = message(text)
            with patch.object(commands.settings, 'telegram_chat_id', 1):
                await commands.cmd_unknown(event)
            event.answer.assert_awaited_once()

    async def test_missing_renpho_measurement_is_not_999_days(self):
        with patch.object(scheduler.db, 'days_since_last_renpho', AsyncMock(return_value=None)), patch.object(scheduler, '_send_markdown', AsyncMock()) as send:
            await scheduler.check_renpho_reminder(SimpleNamespace())
        self.assertNotIn('999', send.call_args.args[1])
        self.assertIn('keine Messung', send.call_args.args[1])

    def test_external_html_and_broken_markdown_are_safe(self):
        self.assertEqual(telegram_html('**Title** <script>&</script> _ok_ google_fit'),
                         '<b>Title</b> &lt;script&gt;&amp;&lt;/script&gt; <i>ok</i> google_fit')
        self.assertEqual(telegram_html('*unfinished [source'), '*unfinished [source')

    def test_activity_rounds_values_and_separates_entries(self):
        text = formatter.activity_list([{'name': 'Test', 'training_effect_aerobic': 2.0999999046, 'training_effect_anaerobic': 0.0}]*2)
        self.assertIn('2.1', text)
        self.assertIn('anaerob: 0', text)
        self.assertNotIn('999', text)
        self.assertIn('\n\n•', text)

    def test_coaching_text_is_not_silently_cut_at_line_limit(self):
        text = '\n'.join('line'+str(i) for i in range(9))
        self.assertIn('line8', '\n'.join(formatter._coach_block(text, max_lines=4)))
