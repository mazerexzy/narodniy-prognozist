from __future__ import annotations

from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message


class IsAdminFilter(BaseFilter):
    """Пропускает только админов. Флаг `is_admin` вычисляет AuthMiddleware
    (ADMIN_IDS из .env + админы, назначенные через бот)."""

    async def __call__(self, event: Message | CallbackQuery, is_admin: bool = False) -> bool:
        return is_admin
