from __future__ import annotations

from typing import Any

from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.ext.asyncio import AsyncSession


class BaseRepository:
    """Репозиторий работает в чужой сессии и никогда не делает commit сам.

    Границы транзакции задаёт UnitOfWork: так сервис может объединить вызовы
    нескольких репозиториев в одну атомарную операцию.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _upsert(self, model: Any) -> Any:
        """INSERT с поддержкой ON CONFLICT для текущей СУБД.

        У SQLite и PostgreSQL одинаковый API (on_conflict_do_nothing /
        on_conflict_do_update), но конструкции живут в разных диалектах.
        """
        dialect = self._session.bind.dialect.name
        if dialect == "postgresql":
            return postgresql.insert(model)
        if dialect == "sqlite":
            return sqlite.insert(model)
        raise NotImplementedError(f"UPSERT не реализован для СУБД {dialect!r}")
