from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import contains_eager

from bot.database.models import Match, Outcome, Prediction, Round, utcnow
from bot.database.repositories.base import BaseRepository


class PredictionRepository(BaseRepository):
    async def upsert(self, user_id: int, match_id: int, outcome: Outcome) -> Prediction:
        """Создаёт прогноз или меняет исход существующего.

        Дедлайн здесь НЕ проверяется — это обязанность сервиса.
        """
        now = utcnow()
        stmt = self._upsert(Prediction).values(
            user_id=user_id, match_id=match_id, outcome=outcome, created_at=now, updated_at=now
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[Prediction.user_id, Prediction.match_id],
            # onupdate в UPSERT не срабатывает, поэтому updated_at задаём явно.
            set_={"outcome": stmt.excluded.outcome, "updated_at": now},
        ).returning(Prediction)
        prediction = await self._session.scalar(stmt, execution_options={"populate_existing": True})
        assert prediction is not None  # DO UPDATE всегда возвращает строку
        return prediction

    async def get(self, user_id: int, match_id: int) -> Prediction | None:
        return await self._session.scalar(
            select(Prediction).where(Prediction.user_id == user_id, Prediction.match_id == match_id)
        )

    async def get_outcomes_for_round(self, user_id: int, round_id: int) -> dict[int, Outcome]:
        """{match_id: исход} — чтобы отметить уже сделанный выбор на клавиатуре тура."""
        result = await self._session.execute(
            select(Prediction.match_id, Prediction.outcome)
            .join(Prediction.match)
            .where(Prediction.user_id == user_id, Match.round_id == round_id)
        )
        return {match_id: outcome for match_id, outcome in result.tuples()}

    async def list_by_user(self, user_id: int, tournament_id: int) -> Sequence[Prediction]:
        """Все прогнозы пользователя в турнире вместе с матчами, свежие сверху."""
        result = await self._session.scalars(
            select(Prediction)
            .join(Prediction.match)
            .join(Match.round)
            .where(Prediction.user_id == user_id, Round.tournament_id == tournament_id)
            .options(contains_eager(Prediction.match))
            .order_by(Match.starts_at.desc(), Match.id.desc())
        )
        return result.all()

    async def count_by_outcome(self, match_id: int) -> dict[Outcome, int]:
        """{исход: число прогнозов} по матчу."""
        result = await self._session.execute(
            select(Prediction.outcome, func.count())
            .where(Prediction.match_id == match_id)
            .group_by(Prediction.outcome)
        )
        return {outcome: count for outcome, count in result.tuples()}
