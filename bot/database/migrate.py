"""Применение миграций Alembic при запуске бота."""

from __future__ import annotations

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
# Схема, которую создавал create_all до появления миграций.
BASELINE_REVISION = "0001"


def _alembic_config(connection: Connection) -> Config:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    config.attributes["connection"] = connection
    config.attributes["configure_logger"] = False   # логирование уже настроено ботом
    return config


def _upgrade(connection: Connection) -> None:
    config = _alembic_config(connection)
    inspector = inspect(connection)
    if inspector.has_table("users") and not inspector.has_table("alembic_version"):
        # База создана старой версией бота (без миграций): отмечаем её как базовую
        # ревизию, а не пытаемся создать таблицы заново.
        logger.warning("База без истории миграций — отмечаю её ревизией %s", BASELINE_REVISION)
        command.stamp(config, BASELINE_REVISION)
    command.upgrade(config, "head")


async def upgrade_database(engine: AsyncEngine) -> None:
    """Доводит схему БД до последней миграции. Безопасно вызывать при каждом старте."""
    async with engine.begin() as connection:
        await connection.run_sync(_upgrade)
