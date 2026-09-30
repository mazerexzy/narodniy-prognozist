"""Права администратора.

Два источника админов:
- ADMIN_IDS в .env — постоянные, через бот их удалить нельзя;
- назначенные через бот любым админом — хранятся в таблице admins.

Bot API не умеет находить пользователя по @username, поэтому ID берётся из
базы: если человек уже запускал бота, права выдаются сразу; если нет —
сохраняется ожидающее приглашение, которое привязывается к его ID при первом
обращении к боту.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.database.models import Admin, User, utcnow
from bot.services.base import BaseService, Clock
from bot.services.errors import AdminNotFoundError, AlreadyAdminError, InvalidUsernameError

# Правила Telegram: 5–32 символа, латиница, цифры, подчёркивание, начинается с буквы.
_USERNAME_RE = re.compile(r"[a-z][a-z0-9_]{4,31}")
_LINK_PREFIXES = ("https://t.me/", "http://t.me/", "t.me/", "@")


def normalize_username(raw: str) -> str:
    """«@Kirill_94», «t.me/kirill_94» → «kirill_94»."""
    username = raw.strip()
    for prefix in _LINK_PREFIXES:
        if username.lower().startswith(prefix):
            username = username[len(prefix):]
            break
    username = username.lower()
    if not _USERNAME_RE.fullmatch(username):
        raise InvalidUsernameError()
    return username


@dataclass(frozen=True, slots=True)
class AdminView:
    admin_id: int | None          # None — админ из .env (удалить через бот нельзя)
    telegram_id: int | None       # None — приглашение ещё не привязано
    username: str | None
    nickname: str | None
    from_config: bool

    @property
    def pending(self) -> bool:
        return self.telegram_id is None


@dataclass(frozen=True, slots=True)
class AdminList:
    config_admins: list[AdminView]
    bot_admins: list[AdminView]


class AdminService(BaseService):
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        config_admin_ids: Iterable[int] = (),
        clock: Clock = utcnow,
    ) -> None:
        super().__init__(session_factory, clock=clock)
        self._config_admin_ids = frozenset(config_admin_ids)

    async def is_admin(self, telegram_id: int, tg_username: str | None) -> bool:
        """Проверка прав на каждый апдейт. Попутно привязывает приглашение по username к ID."""
        if telegram_id in self._config_admin_ids:
            return True
        username = tg_username.lower() if tg_username else None
        async with self._uow() as uow:
            admin = await uow.admins.find(telegram_id, username)
            if admin is None:
                return False
            if admin.telegram_id is None:
                await uow.admins.bind_telegram_id(admin.id, telegram_id)
                await uow.commit()
            return True

    async def list_admins(self) -> AdminList:
        async with self._uow() as uow:
            config_admins = []
            for telegram_id in sorted(self._config_admin_ids):
                user = await uow.users.get(telegram_id)
                config_admins.append(_view(None, telegram_id, user, from_config=True))
            bot_admins = [
                _view(admin, admin.telegram_id, user, from_config=False)
                for admin, user in await uow.admins.list_with_users()
                if admin.telegram_id not in self._config_admin_ids
            ]
            return AdminList(config_admins, bot_admins)

    async def add_admin(self, added_by: int, raw_username: str) -> AdminView:
        username = normalize_username(raw_username)
        async with self._uow() as uow:
            user = await uow.users.get_by_tg_username(username)
            telegram_id = user.telegram_id if user else None
            if telegram_id in self._config_admin_ids or await uow.admins.exists_for(telegram_id, username):
                raise AlreadyAdminError(username)
            admin = await uow.admins.create(telegram_id=telegram_id, username=username, added_by=added_by)
            if admin is None:   # параллельное добавление того же человека
                raise AlreadyAdminError(username)
            await uow.commit()
            return _view(admin, telegram_id, user, from_config=False)

    async def remove_admin(self, admin_id: int) -> AdminView:
        async with self._uow() as uow:
            admin = await uow.admins.delete(admin_id)
            if admin is None:
                raise AdminNotFoundError()
            user = await uow.users.get(admin.telegram_id) if admin.telegram_id else None
            await uow.commit()
            return _view(admin, admin.telegram_id, user, from_config=False)


def _view(admin: Admin | None, telegram_id: int | None, user: User | None, *, from_config: bool) -> AdminView:
    username = (user.tg_username if user and user.tg_username else None) or (admin.username if admin else None)
    return AdminView(
        admin_id=admin.id if admin else None,
        telegram_id=telegram_id,
        username=username,
        nickname=user.nickname if user else None,
        from_config=from_config,
    )
