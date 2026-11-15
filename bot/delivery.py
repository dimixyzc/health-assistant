"""Bounded Telegram delivery; model text is never trusted as Telegram markup."""
import asyncio
from contextvars import ContextVar
from html import escape
import logging
import re

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramBadRequest

logger = logging.getLogger(__name__)
_progress = ContextVar('telegram_progress', default=None)


def chunks(text: str, limit: int = 1800) -> list[str]:
    # 1800 Unicode codepoints stay below 4096 UTF-16 units, even with emoji.
    text = text.strip() or '⚠️ Die Antwort ist gerade nicht verfügbar. Bitte versuche es später erneut.'
    result = []
    while len(text) > limit:
        end = text.rfind('\n', 0, limit + 1)
        if end < limit // 2:
            end = text.rfind(' ', 0, limit + 1)
        if end < limit // 2:
            end = limit
        result.append(text[:end])
        text = text[end:].lstrip('\n ')
    if text:
        result.append(text)
    return result


def telegram_html(text: str) -> str:
    """Render a small safe Markdown subset, escaping all external HTML."""
    text = re.sub(r'^#{1,6}\s+(.+)$', r'**\1**', text, flags=re.M)
    tokens = re.compile(r'`([^`\n]+)`|\*\*([^*\n]+)\*\*|(?<![\w*])\*([^*\n]+)\*(?!\w)|(?<!\w)_([^_\n]+)_(?!\w)|\\([_*`\[\\])')
    parts, pos = [], 0
    for match in tokens.finditer(text):
        parts.append(escape(text[pos:match.start()]))
        groups = match.groups()
        index = next(i for i, value in enumerate(groups) if value is not None)
        value = escape(groups[index])
        tag = {0: 'code', 1: 'b', 2: 'b', 3: 'i'}.get(index)
        parts.append(f'<{tag}>{value}</{tag}>' if tag else value)
        pos = match.end()
    parts.append(escape(text[pos:]))
    return ''.join(parts)


async def send_text(send, text: str, *, edit=None):
    for index, part in enumerate(chunks(text)):
        target = edit if index == 0 and edit is not None else send
        try:
            await target(telegram_html(part), parse_mode='HTML')
        except TelegramBadRequest as exc:
            reason = str(exc).lower()
            if 'message is not modified' in reason:
                continue
            if target is edit:
                # The placeholder may have been removed or become uneditable.
                await send(telegram_html(part), parse_mode='HTML')
            elif "can't parse entities" in reason:
                await send(part, parse_mode=None)
            else:
                raise


async def progress(message, text: str) -> None:
    state = _progress.get()
    sent = await message.answer(text, parse_mode=None)
    if state is not None:
        state['message'] = sent


async def answer(message, text: str) -> None:
    state = _progress.get()
    pending = state.pop('message', None) if state is not None else None
    await send_text(message.answer, text, edit=pending.edit_text if pending else None)


class ReplyMiddleware(BaseMiddleware):
    """Ensure handler bugs and stalled providers produce a visible final reply."""
    def __init__(self, chat_id: int | None, timeout: float = 80):
        self.chat_id = chat_id
        self.timeout = timeout

    async def __call__(self, handler, event, data):
        if event.chat.id != self.chat_id:
            return
        token = _progress.set({})
        try:
            return await asyncio.wait_for(handler(event, data), timeout=self.timeout)
        except TimeoutError:
            logger.warning('Telegram request deadline exceeded')
            await answer(event, '⌛ Die Abfrage dauert gerade zu lange. Bitte versuche es gleich erneut. /status zeigt deine verfügbaren Tageswerte.')
        except Exception as exc:
            # Do not log message bodies, credentials or provider response bodies.
            logger.error('Telegram handler failed: %s', type(exc).__name__)
            await answer(event, '⚠️ Bei der Verarbeitung ist ein technischer Fehler aufgetreten. Bitte versuche es erneut oder nutze /hilfe.')
        finally:
            _progress.reset(token)
