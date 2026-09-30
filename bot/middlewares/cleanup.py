"""Чистота чата: в личке остаётся только актуальный «экран».

Как только бот отправляет новое сообщение, из чата удаляются его прошлые
сообщения и присланные с тех пор сообщения пользователя (нажатия кнопок меню,
команды, введённые данные).

Исключения:
- подсказки и ошибки отправляются внутри `keep_history()` — они ничего не
  удаляют, чтобы пользователь видел свой ввод и мог его исправить;
- сообщение с нижним меню (ReplyKeyboardMarkup) не удаляется при обычной
  чистке: клиенты Telegram прячут клавиатуру, если удалить сообщение, которое
  её прислало. Оно заменяется только следующим сообщением с меню.

История хранится в памяти процесса: после перезапуска бота сообщения,
отправленные до него, не удаляются.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from aiogram import BaseMiddleware, Bot
from aiogram.client.session.middlewares.base import BaseRequestMiddleware, NextRequestMiddlewareType
from aiogram.enums import ChatType
from aiogram.methods import DeleteMessages, SendMessage, TelegramMethod
from aiogram.methods.base import TelegramType
from aiogram.types import Message, ReplyKeyboardMarkup, TelegramObject

logger = logging.getLogger(__name__)

_MAX_TRACKED = 100          # лимит deleteMessages за один вызов
_keep_history: ContextVar[bool] = ContextVar("keep_history", default=False)


@contextmanager
def keep_history() -> Iterator[None]:
    """Сообщения, отправленные внутри блока, не удаляют предыдущие."""
    token = _keep_history.set(True)
    try:
        yield
    finally:
        _keep_history.reset(token)


class ChatHistory:
    def __init__(self) -> None:
        self._pending: dict[int, list[int]] = {}   # chat_id -> id сообщений на удаление
        self._menu: dict[int, int] = {}            # chat_id -> id сообщения с нижним меню

    def remember(self, chat_id: int, message_id: int) -> None:
        pending = self._pending.setdefault(chat_id, [])
        pending.append(message_id)
        del pending[:-_MAX_TRACKED]

    def take(self, chat_id: int) -> list[int]:
        return self._pending.pop(chat_id, [])

    def replace_menu(self, chat_id: int, message_id: int) -> int | None:
        previous = self._menu.get(chat_id)
        self._menu[chat_id] = message_id
        return previous


class TrackIncomingMiddleware(BaseMiddleware):
    """Запоминает входящие сообщения пользователя — их удалит следующий экран."""

    def __init__(self, history: ChatHistory) -> None:
        self._history = history

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Message) and event.chat.type == ChatType.PRIVATE:
            self._history.remember(event.chat.id, event.message_id)
        return await handler(event, data)


class CleanupRequestMiddleware(BaseRequestMiddleware):
    """Перехватывает sendMessage и после успешной отправки чистит старое."""

    def __init__(self, history: ChatHistory) -> None:
        self._history = history

    async def __call__(
        self,
        make_request: NextRequestMiddlewareType[TelegramType],
        bot: Bot,
        method: TelegramMethod[TelegramType],
    ) -> Any:
        response = await make_request(bot, method)
        if not isinstance(method, SendMessage):
            return response
        message = getattr(response, "result", response)
        if not isinstance(message, Message) or message.chat.type != ChatType.PRIVATE:
            return response

        chat_id = message.chat.id
        to_delete = [] if _keep_history.get() else self._history.take(chat_id)
        if isinstance(method.reply_markup, ReplyKeyboardMarkup):
            previous_menu = self._history.replace_menu(chat_id, message.message_id)
            if previous_menu is not None:
                to_delete.append(previous_menu)
        else:
            self._history.remember(chat_id, message.message_id)

        if to_delete:
            try:
                # Сообщения старше 48 ч Telegram молча пропускает.
                await bot(DeleteMessages(chat_id=chat_id, message_ids=to_delete))
            except Exception:
                logger.warning("Не удалось удалить старые сообщения в чате %s", chat_id, exc_info=True)
        return response
