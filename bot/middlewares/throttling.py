from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, TelegramObject
from aiogram.types import User as TgUser

from bot.utils import texts

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


class ThrottlingMiddleware(BaseMiddleware):
    """Отбрасывает апдейты пользователя, пришедшие чаще, чем раз в `rate` секунд.

    Хранилище — в памяти процесса; для одного инстанса бота этого достаточно.
    """

    _PRUNE_THRESHOLD = 10_000

    def __init__(self, rate: float = 0.3) -> None:
        self._rate = rate
        self._last_seen: dict[int, float] = {}

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        tg_user: TgUser | None = data.get("event_from_user")
        if tg_user is None or self._rate <= 0:
            return await handler(event, data)

        now = time.monotonic()
        last = self._last_seen.get(tg_user.id)
        if last is not None and now - last < self._rate:
            if isinstance(event, CallbackQuery):
                await event.answer(texts.TOO_FAST)   # иначе у кнопки крутятся «часики»
            return None

        self._last_seen[tg_user.id] = now
        if len(self._last_seen) > self._PRUNE_THRESHOLD:
            self._last_seen = {uid: t for uid, t in self._last_seen.items() if now - t < self._rate}
        return await handler(event, data)
