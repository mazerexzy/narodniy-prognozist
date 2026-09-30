from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.database.models import utcnow
from bot.database.repositories import UnitOfWork

Clock = Callable[[], datetime]


class BaseService:
    """Каждый публичный метод сервиса — одна транзакция (свой UnitOfWork).

    `clock` подменяется в тестах, чтобы проверять дедлайны без ожидания.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession], *, clock: Clock = utcnow) -> None:
        self._session_factory = session_factory
        self._clock = clock

    def _uow(self) -> UnitOfWork:
        return UnitOfWork(self._session_factory)

    def _now(self) -> datetime:
        return self._clock()
