from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import delete, select, update
from sqlalchemy.orm import selectinload

from bot.database.models import Round
from bot.database.repositories.base import BaseRepository


class RoundRepository(BaseRepository):
    async def get(self, round_id: int) -> Round | None:
        return await self._session.get(Round, round_id)

    async def get_with_matches(self, round_id: int) -> Round | None:
        return await self._session.scalar(
            select(Round).where(Round.id == round_id).options(selectinload(Round.matches))
        )

    async def create(self, tournament_id: int, title: str, deadline_at: datetime) -> Round:
        round_ = Round(tournament_id=tournament_id, title=title, deadline_at=deadline_at)
        self._session.add(round_)
        await self._session.flush()
        return round_

    async def list_by_tournament(self, tournament_id: int) -> Sequence[Round]:
        result = await self._session.scalars(
            select(Round).where(Round.tournament_id == tournament_id).order_by(Round.deadline_at, Round.id)
        )
        return result.all()

    async def list_open(self, tournament_id: int, now: datetime) -> Sequence[Round]:
        """Туры, по которым ещё принимаются прогнозы."""
        result = await self._session.scalars(
            select(Round)
            .where(Round.tournament_id == tournament_id, Round.deadline_at > now)
            .order_by(Round.deadline_at, Round.id)
        )
        return result.all()

    async def set_deadline(self, round_id: int, deadline_at: datetime) -> bool:
        result = await self._session.execute(
            update(Round).where(Round.id == round_id).values(deadline_at=deadline_at)
        )
        return result.rowcount > 0

    async def delete(self, round_id: int) -> bool:
        """Удаляет тур вместе с матчами и прогнозами (ON DELETE CASCADE)."""
        result = await self._session.execute(delete(Round).where(Round.id == round_id))
        return result.rowcount > 0
