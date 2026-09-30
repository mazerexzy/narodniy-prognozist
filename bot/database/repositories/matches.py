from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import joinedload

from bot.database.models import Match, MatchStatus, Outcome, Round
from bot.database.repositories.base import BaseRepository


@dataclass(frozen=True, slots=True)
class NewMatch:
    """Данные матча для массовой загрузки (результат парсинга сообщения админа)."""

    home_team: str
    away_team: str
    starts_at: datetime


class MatchRepository(BaseRepository):
    async def get(self, match_id: int) -> Match | None:
        return await self._session.get(Match, match_id)

    async def get_with_round(self, match_id: int) -> Match | None:
        """Матч вместе с туром — нужен для проверки дедлайна при приёме ставки."""
        return await self._session.scalar(
            select(Match).where(Match.id == match_id).options(joinedload(Match.round))
        )

    async def create_many(self, round_id: int, matches: Sequence[NewMatch]) -> list[Match]:
        objects = [
            Match(round_id=round_id, home_team=m.home_team, away_team=m.away_team, starts_at=m.starts_at)
            for m in matches
        ]
        self._session.add_all(objects)
        await self._session.flush()
        return objects

    async def list_by_round(self, round_id: int) -> Sequence[Match]:
        result = await self._session.scalars(
            select(Match).where(Match.round_id == round_id).order_by(Match.starts_at, Match.id)
        )
        return result.all()

    async def list_awaiting_result(self, tournament_id: int, now: datetime) -> Sequence[Match]:
        """Начавшиеся матчи турнира без результата — очередь для админа."""
        result = await self._session.scalars(
            select(Match)
            .join(Match.round)
            .where(
                Round.tournament_id == tournament_id,
                Match.status == MatchStatus.SCHEDULED,
                Match.starts_at <= now,
            )
            .order_by(Match.starts_at, Match.id)
        )
        return result.all()

    async def count_unsettled(self, tournament_id: int) -> int:
        """Матчи турнира, по которым ещё нет ни результата, ни отмены."""
        stmt = (
            select(func.count())
            .select_from(Match)
            .join(Match.round)
            .where(Round.tournament_id == tournament_id, Match.status == MatchStatus.SCHEDULED)
        )
        return await self._session.scalar(stmt) or 0

    async def get_earliest_start(self, round_id: int) -> datetime | None:
        """Старт первого матча тура — из него вычисляется дедлайн."""
        return await self._session.scalar(select(func.min(Match.starts_at)).where(Match.round_id == round_id))

    async def set_result(self, match_id: int, result: Outcome) -> bool:
        """Вносит или исправляет результат. Рейтинг пересчитается сам: очки не хранятся."""
        res = await self._session.execute(
            update(Match)
            .where(Match.id == match_id)
            .values(result=result, status=MatchStatus.FINISHED)
        )
        return res.rowcount > 0

    async def cancel(self, match_id: int) -> bool:
        """Отменяет матч: результат сбрасывается, баллы за него не начисляются."""
        res = await self._session.execute(
            update(Match)
            .where(Match.id == match_id)
            .values(result=None, status=MatchStatus.CANCELLED)
        )
        return res.rowcount > 0

    async def delete(self, match_id: int) -> bool:
        res = await self._session.execute(delete(Match).where(Match.id == match_id))
        return res.rowcount > 0
