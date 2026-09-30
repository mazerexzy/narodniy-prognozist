from aiogram import Router

from bot.filters.is_admin import IsAdminFilter
from bot.handlers.admin import admins, delete_match, matches, menu, results, tournament


def setup_admin_router() -> Router:
    """Фильтр на родительском роутере закрывает все вложенные: если он не
    прошёл, aiogram не спускается в sub_routers."""
    router = Router(name="admin")
    router.message.filter(IsAdminFilter())
    router.callback_query.filter(IsAdminFilter())
    router.include_routers(
        menu.router, matches.router, delete_match.router, results.router, tournament.router, admins.router
    )
    return router
