from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select, update

from bot.database.models import Tournament, TournamentStatus, utcnow
from bot.database.repositories.base import BaseRepository


class TournamentRepository(BaseRepository):
    async def get(self, tournament_id: int) -> Tournament | None:
        return await self._session.get(Tournament, tournament_id)

    async def get_active(self) -> Tournament | None:
        return await self._session.scalar(
            select(Tournament).where(Tournament.status == TournamentStatus.ACTIVE)
        )

    async def create(self, title: str) -> Tournament | None:
        """Создаёт активный турнир. None — активный турнир уже существует."""
        stmt = self._upsert(Tournament).values(title=title).on_conflict_do_nothing().returning(Tournament)
        return await self._session.scalar(stmt)

    async def archive(self, tournament_id: int, archived_at: datetime | None = None) -> bool:
        """Переводит активный турнир в архив. False — турнир не найден или уже в архиве."""
        result = await self._session.execute(
            update(Tournament)
            .where(Tournament.id == tournament_id, Tournament.status == TournamentStatus.ACTIVE)
            .values(status=TournamentStatus.ARCHIVED, archived_at=archived_at or utcnow())
        )
        return result.rowcount > 0

    async def list_archived(self, *, limit: int = 10, offset: int = 0) -> Sequence[Tournament]:
        result = await self._session.scalars(
            select(Tournament)
            .where(Tournament.status == TournamentStatus.ARCHIVED)
            .order_by(Tournament.archived_at.desc(), Tournament.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return result.all()

    async def count_archived(self) -> int:
        stmt = select(func.count()).where(Tournament.status == TournamentStatus.ARCHIVED)
        return await self._session.scalar(stmt) or 0
