"""Точка входа: python -m bot"""

from __future__ import annotations

import asyncio
import logging
import sys

from aiogram.exceptions import TelegramUnauthorizedError
from pydantic import ValidationError

from bot.config import Settings
from bot.database import create_engine, create_session_factory, upgrade_database
from bot.loader import create_bot, create_dispatcher, create_storage, setup_bot_profile
from bot.middlewares.cleanup import ChatHistory
from bot.services import Services

logger = logging.getLogger("bot")


async def run(settings: Settings) -> None:
    engine = create_engine(settings.database_url)
    await upgrade_database(engine)
    services = Services.create(create_session_factory(engine), admin_ids=settings.admin_ids)

    history = ChatHistory()
    bot = create_bot(settings.bot_token.get_secret_value(), history)
    dp = create_dispatcher(
        services, history=history, storage=create_storage(settings.redis_url)
    )
    try:
        me = await bot.get_me()
        logger.info(
            "Бот @%s запущен | БД: %s | FSM: %s | админов в .env: %d",
            me.username,
            engine.url.render_as_string(hide_password=True),
            "Redis" if settings.redis_url else "память",
            len(settings.admin_ids),
        )
        await setup_bot_profile(bot)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await dp.storage.close()
        await bot.session.close()
        await engine.dispose()


def main() -> None:
    try:
        settings = Settings()
    except ValidationError as e:
        sys.exit(f"Ошибка конфигурации — проверьте файл .env (образец: .env.example):\n{e}")

    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    if not settings.admin_ids:
        logger.warning("ADMIN_IDS не задан — админка будет недоступна")

    try:
        asyncio.run(run(settings))
    except TelegramUnauthorizedError:
        sys.exit("Telegram отклонил BOT_TOKEN — проверьте токен в .env (выдаёт @BotFather)")
    except KeyboardInterrupt:
        logger.info("Остановлено")


if __name__ == "__main__":
    main()
