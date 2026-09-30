from aiogram import Router

from bot.handlers import errors, fallback
from bot.handlers.admin import setup_admin_router
from bot.handlers.user import leaderboard, matches, my_bets, start


def setup_routers() -> Router:
    """Порядок важен: первым подходящим хэндлером обрабатывается апдейт.

    Пользовательские кнопки меню стоят раньше админских состояний, поэтому
    нажатие «⚽ Матчи» посреди админского диалога не примется за список матчей.
    fallback — строго последним.
    """
    root = Router(name="root")
    root.include_routers(
        errors.router,
        start.router,
        matches.router,
        my_bets.router,
        leaderboard.router,
        setup_admin_router(),
        fallback.router,
    )
    return root
