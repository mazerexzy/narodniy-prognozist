from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import exists, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import aliased

from bot.database.models import User, make_nickname_key
from bot.database.repositories.base import BaseRepository


class UserRepository(BaseRepository):
    async def get(self, telegram_id: int) -> User | None:
        return await self._session.get(User, telegram_id)

    async def get_by_nickname(self, nickname: str) -> User | None:
        # Поиск по ключу: без учёта регистра в любом алфавите.
        return await self._session.scalar(select(User).where(User.nickname_key == make_nickname_key(nickname)))

    async def get_by_tg_username(self, username: str) -> User | None:
        """Поиск по @username без учёта регистра (username — без @)."""
        return await self._session.scalar(
            select(User).where(func.lower(User.tg_username) == username.lower()).limit(1)
        )

    async def is_nickname_taken(self, nickname: str, *, exclude_user_id: int | None = None) -> bool:
        condition = User.nickname_key == make_nickname_key(nickname)
        if exclude_user_id is not None:
            condition &= User.telegram_id != exclude_user_id
        return bool(await self._session.scalar(select(exists().where(condition))))

    async def create(self, telegram_id: int, nickname: str, tg_username: str | None = None) -> User | None:
        """Создаёт пользователя. Возвращает None, если такой ID или ник уже есть.

        ON CONFLICT DO NOTHING вместо перехвата IntegrityError: гонка двух
        регистраций с одним ником не ломает транзакцию, сервис просто получает None.
        """
        stmt = (
            self._upsert(User)
            .values(
                telegram_id=telegram_id,
                nickname=nickname,
                nickname_key=make_nickname_key(nickname),
                tg_username=tg_username,
            )
            .on_conflict_do_nothing()
            .returning(User)
        )
        return await self._session.scalar(stmt)

    async def update_nickname(self, telegram_id: int, nickname: str) -> bool:
        """Меняет ник. False — пользователь не найден или ник занят.

        Занятость проверяется в том же UPDATE (NOT EXISTS). Если параллельный
        запрос успел занять ник между проверкой и записью, сработает UNIQUE —
        тоже вернём False. После такого False транзакция может быть прервана
        (PostgreSQL), поэтому вызывающий код не должен продолжать работу с БД.
        """
        key = make_nickname_key(nickname)
        other = aliased(User)  # без алиаса подзапрос скоррелируется с обновляемой строкой
        taken = exists().where(other.nickname_key == key, other.telegram_id != telegram_id)
        stmt = (
            update(User)
            .where(User.telegram_id == telegram_id, ~taken)
            .values(nickname=nickname, nickname_key=key)
            .returning(User.telegram_id)
            .execution_options(synchronize_session="fetch")
        )
        try:
            return await self._session.scalar(stmt) is not None
        except IntegrityError:
            return False

    async def update_tg_username(self, telegram_id: int, tg_username: str | None) -> None:
        await self._session.execute(
            update(User)
            .where(User.telegram_id == telegram_id, User.tg_username.is_distinct_from(tg_username))
            .values(tg_username=tg_username)
        )

    async def set_banned(self, telegram_id: int, is_banned: bool) -> bool:
        result = await self._session.execute(
            update(User).where(User.telegram_id == telegram_id).values(is_banned=is_banned)
        )
        return result.rowcount > 0

    async def list_active_ids(self) -> Sequence[int]:
        """ID всех незабаненных пользователей (для рассылок)."""
        result = await self._session.scalars(
            select(User.telegram_id).where(User.is_banned.is_(False)).order_by(User.telegram_id)
        )
        return result.all()

    async def count(self) -> int:
        return await self._session.scalar(select(func.count()).select_from(User)) or 0
