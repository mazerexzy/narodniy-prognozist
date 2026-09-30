from __future__ import annotations

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from bot.handlers import setup_routers
from bot.middlewares.auth import AuthMiddleware
from bot.middlewares.cleanup import ChatHistory, CleanupRequestMiddleware, TrackIncomingMiddleware
from bot.middlewares.throttling import ThrottlingMiddleware
from bot.services import Services

BOT_COMMANDS = [
    BotCommand(command="start", description="Главное меню"),
    BotCommand(command="help", description="Правила игры"),
    BotCommand(command="cancel", description="Отменить текущее действие"),
]


# Экран «Что умеет этот бот?» до нажатия «Старт» и подпись в профиле бота.
BOT_DESCRIPTION = (
    "«Народный прогнозист» — турнир прогнозов на спортивные матчи.\n\n"
    "Угадывайте исходы матчей: П1, Х или П2. За каждый верный прогноз начисляется 1 балл, "
    "лучшие участники занимают верхние строки таблицы лидеров.\n\n"
    "Нажмите «Старт», чтобы принять участие."
)
BOT_SHORT_DESCRIPTION = "Турнир прогнозов на спортивные матчи: П1, Х, П2. 1 балл за каждый верный исход."


async def setup_bot_profile(bot: Bot) -> None:
    """Команды меню и описание бота. Описание ставится, только если в BotFather
    оно пустое, — заданное владельцем бота не перезаписываем."""
    await bot.set_my_commands(BOT_COMMANDS)
    if not (await bot.get_my_description()).description:
        await bot.set_my_description(BOT_DESCRIPTION)
    if not (await bot.get_my_short_description()).short_description:
        await bot.set_my_short_description(BOT_SHORT_DESCRIPTION)


def create_storage(redis_url: str | None) -> BaseStorage:
    """Redis — состояния диалогов переживают перезапуск; без него — память процесса."""
    if not redis_url:
        return MemoryStorage()
    from aiogram.fsm.storage.redis import RedisStorage

    return RedisStorage.from_url(redis_url)


def create_bot(token: str, history: ChatHistory | None = None) -> Bot:
    bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    if history is not None:
        bot.session.middleware(CleanupRequestMiddleware(history))
    return bot


def create_dispatcher(
    services: Services,
    *,
    history: ChatHistory | None = None,
    storage: BaseStorage | None = None,
    throttle_rate: float = 0.3,
) -> Dispatcher:
    # services попадает в workflow_data: хэндлеры, фильтры и middleware
    # получают его по имени аргумента.
    dp = Dispatcher(storage=storage or MemoryStorage(), services=services)

    if history is not None:
        # Первым: запоминаем даже те сообщения, которые отсеет throttling.
        dp.message.outer_middleware(TrackIncomingMiddleware(history))
    for observer in (dp.message, dp.callback_query):
        observer.outer_middleware(ThrottlingMiddleware(throttle_rate))
        observer.outer_middleware(AuthMiddleware())

    dp.include_router(setup_routers())
    return dp
