from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Subquery, and_, case, func, insert, literal, select

from bot.database.models import LeaderboardSnapshot, Match, MatchStatus, Prediction, Round, User
from bot.database.repositories.base import BaseRepository


@dataclass(frozen=True, slots=True)
class Standing:
    place: int
    user_id: int
    nickname: str
    points: int
    predictions_count: int
    # Контакт для админов (текущий @username из профиля). Участникам не показывается.
    tg_username: str | None = None


class LeaderboardRepository(BaseRepository):
    """Живой рейтинг активного турнира и замороженные таблицы архивных."""

    @staticmethod
    def _standings(tournament_id: int) -> Subquery:
        # Очки не хранятся: балл — это прогноз, совпавший с результатом завершённого матча.
        points = func.coalesce(
            func.sum(
                case(
                    (and_(Match.status == MatchStatus.FINISHED, Prediction.outcome == Match.result), 1),
                    else_=0,
                )
            ),
            0,
        )
        return (
            select(
                # RANK: равные очки делят место, следующее место пропускается (1, 1, 3).
                func.rank().over(order_by=points.desc()).label("place"),
                User.telegram_id.label("user_id"),
                User.nickname.label("nickname"),
                points.label("points"),
                func.count(Prediction.id).label("predictions_count"),
                User.tg_username.label("tg_username"),
            )
            .select_from(User)
            .join(Prediction, Prediction.user_id == User.telegram_id)
            .join(Match, Match.id == Prediction.match_id)
            .join(Round, Round.id == Match.round_id)
            .where(Round.tournament_id == tournament_id, User.is_banned.is_(False))
            .group_by(User.telegram_id)
            .subquery("standings")
        )

    async def get_standings(
        self, tournament_id: int, *, limit: int | None = None, offset: int = 0
    ) -> list[Standing]:
        """Рейтинг турнира. Место считается по всей таблице, а не по странице."""
        sub = self._standings(tournament_id)
        stmt = select(sub).order_by(sub.c.place, sub.c.nickname).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return [Standing(**row) for row in result.mappings()]

    async def get_user_standing(self, tournament_id: int, user_id: int) -> Standing | None:
        sub = self._standings(tournament_id)
        row = (await self._session.execute(select(sub).where(sub.c.user_id == user_id))).mappings().first()
        return Standing(**row) if row else None

    async def count_participants(self, tournament_id: int) -> int:
        sub = self._standings(tournament_id)
        return await self._session.scalar(select(func.count()).select_from(sub)) or 0

    async def save_snapshot(self, tournament_id: int) -> int:
        """Замораживает текущий рейтинг турнира. Возвращает число сохранённых строк."""
        sub = self._standings(tournament_id)
        stmt = insert(LeaderboardSnapshot).from_select(
            ["tournament_id", "place", "user_id", "nickname", "points", "predictions_count"],
            select(
                literal(tournament_id),
                sub.c.place,
                sub.c.user_id,
                sub.c.nickname,
                sub.c.points,
                sub.c.predictions_count,
            ),
        )
        result = await self._session.execute(stmt)
        return result.rowcount

    async def count_snapshot(self, tournament_id: int) -> int:
        stmt = select(func.count()).where(LeaderboardSnapshot.tournament_id == tournament_id)
        return await self._session.scalar(stmt) or 0

    async def get_snapshot_entry(self, tournament_id: int, user_id: int) -> Standing | None:
        stmt = self._snapshot_query(tournament_id).where(LeaderboardSnapshot.user_id == user_id)
        row = (await self._session.execute(stmt)).first()
        return self._from_snapshot(*row) if row else None

    @staticmethod
    def _snapshot_query(tournament_id: int):  # noqa: ANN205 — Select[tuple[...]]
        return (
            select(LeaderboardSnapshot, User.tg_username)
            .join(User, User.telegram_id == LeaderboardSnapshot.user_id)
            .where(LeaderboardSnapshot.tournament_id == tournament_id)
        )

    @staticmethod
    def _from_snapshot(row: LeaderboardSnapshot, tg_username: str | None) -> Standing:
        return Standing(
            place=row.place,
            user_id=row.user_id,
            nickname=row.nickname,
            points=row.points,
            predictions_count=row.predictions_count,
            tg_username=tg_username,
        )

    async def get_snapshot(
        self, tournament_id: int, *, limit: int | None = None, offset: int = 0
    ) -> list[Standing]:
        """Рейтинг архивного турнира в том же формате, что и живой."""
        result = await self._session.execute(
            self._snapshot_query(tournament_id)
            .order_by(LeaderboardSnapshot.place, LeaderboardSnapshot.nickname)
            .limit(limit)
            .offset(offset)
        )
        return [self._from_snapshot(snapshot, tg_username) for snapshot, tg_username in result.tuples()]
