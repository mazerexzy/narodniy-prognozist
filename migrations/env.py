"""Окружение Alembic: работает и из командной строки, и из кода бота.

- `alembic upgrade head` — подключается по DATABASE_URL из .env;
- bot/database/migrate.py передаёт готовое соединение через
  config.attributes["connection"], чтобы не открывать второй event loop.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection

from bot.config import DatabaseSettings
from bot.database.engine import create_engine
from bot.database.models import Base

config = context.config
if config.config_file_name and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _configure(**kwargs: object) -> None:
    context.configure(
        target_metadata=target_metadata,
        compare_type=True,
        # SQLite не умеет ALTER для большинства изменений — Alembic пересоздаёт таблицу.
        render_as_batch=True,
        **kwargs,
    )


def do_run_migrations(connection: Connection) -> None:
    _configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    engine = create_engine(DatabaseSettings().database_url)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(do_run_migrations)
            await connection.commit()
    finally:
        await engine.dispose()


def run_migrations_offline() -> None:
    _configure(url=DatabaseSettings().database_url, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
elif (connection := config.attributes.get("connection")) is not None:
    do_run_migrations(connection)
else:
    asyncio.run(run_async_migrations())
