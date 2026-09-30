from __future__ import annotations

from typing import Annotated, Any

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def normalize_database_url(url: str) -> str:
    """Приводит URL к асинхронному драйверу.

    Хостинги обычно выдают `postgres://…` или `postgresql://…` — подставляем asyncpg.
    """
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+asyncpg://" + url[len(prefix):]
    if url.startswith("sqlite:///"):
        return "sqlite+aiosqlite:///" + url[len("sqlite:///"):]
    return url


class DatabaseSettings(BaseSettings):
    """Только подключение к БД — этого достаточно для команд `alembic`."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Разработка: sqlite+aiosqlite:///data/bot.db
    # Продакшн:   postgresql://user:password@host:5432/dbname
    database_url: str = "sqlite+aiosqlite:///data/bot.db"

    @field_validator("database_url")
    @classmethod
    def _normalize_database_url(cls, value: str) -> str:
        return normalize_database_url(value)


class Settings(DatabaseSettings):
    """Настройки из переменных окружения или файла .env в корне проекта."""

    bot_token: SecretStr
    # ADMIN_IDS=123456789,987654321 — постоянные админы; остальных назначают через бот
    admin_ids: Annotated[frozenset[int], NoDecode] = frozenset()
    # Необязательно: redis://host:6379/0 — FSM-состояния переживают перезапуск бота.
    redis_url: str | None = None
    log_level: str = "INFO"

    @field_validator("admin_ids", mode="before")
    @classmethod
    def _split_admin_ids(cls, value: Any) -> Any:
        if isinstance(value, str):
            return frozenset(int(part) for part in value.replace(";", ",").split(",") if part.strip())
        return value

    @field_validator("redis_url", mode="before")
    @classmethod
    def _empty_redis_is_none(cls, value: Any) -> Any:
        return value or None
