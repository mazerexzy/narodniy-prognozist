"""Асинхронный движок (SQLite или PostgreSQL) и фабрика сессий."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import event, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from bot.config import normalize_database_url

SQLITE_PRAGMAS = (
    "PRAGMA foreign_keys = ON",      # в SQLite по умолчанию выключены, иначе CASCADE не работает
    "PRAGMA journal_mode = WAL",     # чтения не блокируются записью
    "PRAGMA synchronous = NORMAL",   # безопасно в режиме WAL и заметно быстрее FULL
    "PRAGMA busy_timeout = 5000",    # ждать блокировку до 5 с вместо мгновенного "database is locked"
)


def _set_sqlite_pragmas(dbapi_connection: Any, _connection_record: Any) -> None:
    cursor = dbapi_connection.cursor()
    try:
        for pragma in SQLITE_PRAGMAS:
            cursor.execute(pragma)
    finally:
        cursor.close()


def create_engine(database_url: str, *, echo: bool = False) -> AsyncEngine:
    url = make_url(normalize_database_url(database_url))   # postgres:// → postgresql+asyncpg://

    if url.get_backend_name() == "sqlite":
        if url.database and url.database != ":memory:":
            Path(url.database).parent.mkdir(parents=True, exist_ok=True)
        engine = create_async_engine(url, echo=echo)
        # PRAGMA действуют на уровне соединения, поэтому выставляем их на каждом новом.
        event.listen(engine.sync_engine, "connect", _set_sqlite_pragmas)
        return engine

    # PostgreSQL: pre_ping отбрасывает соединения, закрытые сервером (рестарт БД,
    # таймаут простоя у хостинга), recycle — страховка от тех же обрывов.
    return create_async_engine(url, echo=echo, pool_pre_ping=True, pool_recycle=1800)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    # expire_on_commit=False: после commit объекты остаются доступны для чтения
    # в хэндлере без повторного (и в async запрещённого неявного) запроса к БД.
    return async_sessionmaker(engine, expire_on_commit=False)
