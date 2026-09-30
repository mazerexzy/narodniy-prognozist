from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import and_, delete, or_, select, update

from bot.database.models import Admin, User
from bot.database.repositories.base import BaseRepository


class AdminRepository(BaseRepository):
    async def list_with_users(self) -> Sequence[tuple[Admin, User | None]]:
        result = await self._session.execute(
            select(Admin, User)
            .outerjoin(User, User.telegram_id == Admin.telegram_id)
            .order_by(Admin.created_at, Admin.id)
        )
        return result.tuples().all()

    async def find(self, telegram_id: int, username: str | None) -> Admin | None:
        """Запись по ID или ожидающее приглашение по username (username — в нижнем регистре)."""
        condition = Admin.telegram_id == telegram_id
        if username:
            condition = or_(condition, and_(Admin.telegram_id.is_(None), Admin.username == username))
        return await self._session.scalar(select(Admin).where(condition).limit(1))

    async def exists_for(self, telegram_id: int | None, username: str | None) -> bool:
        conditions = []
        if telegram_id is not None:
            conditions.append(Admin.telegram_id == telegram_id)
        if username:
            conditions.append(Admin.username == username)
        if not conditions:
            return False
        return await self._session.scalar(select(Admin.id).where(or_(*conditions)).limit(1)) is not None

    async def create(self, *, telegram_id: int | None, username: str | None, added_by: int) -> Admin | None:
        """None — такой админ уже есть (конфликт по ID или username)."""
        stmt = (
            self._upsert(Admin)
            .values(telegram_id=telegram_id, username=username, added_by=added_by)
            .on_conflict_do_nothing()
            .returning(Admin)
        )
        return await self._session.scalar(stmt)

    async def bind_telegram_id(self, admin_id: int, telegram_id: int) -> None:
        await self._session.execute(update(Admin).where(Admin.id == admin_id).values(telegram_id=telegram_id))

    async def delete(self, admin_id: int) -> Admin | None:
        """Удаляет и возвращает удалённую запись (None — не найдена)."""
        return await self._session.scalar(delete(Admin).where(Admin.id == admin_id).returning(Admin))
