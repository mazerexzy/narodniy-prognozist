from __future__ import annotations

from dataclasses import dataclass

from bot.database.models import Match, Outcome, TournamentStatus
from bot.database.repositories import UnitOfWork
from bot.services.base import BaseService
from bot.services.errors import (
    MatchNotFoundError,
    MatchNotStartedError,
    NoActiveTournamentError,
    TournamentArchivedError,
)
from bot.services.scoring import POINTS_PER_HIT, parse_outcome


@dataclass(frozen=True, slots=True)
class ResultSummary:
    """Итог внесения результата — для ответа админу."""

    match: Match
    result: Outcome
    predictions_total: int
    hits: int                 # сколько участников угадали

    @property
    def points_awarded(self) -> int:
        return self.hits * POINTS_PER_HIT


class ResultsService(BaseService):
    """Внесение результатов. Баллы начисляются автоматически: рейтинг считается
    из прогнозов и результатов, поэтому исправление результата сразу
    пересчитывает таблицу."""

    async def list_awaiting_results(self) -> list[Match]:
        async with self._uow() as uow:
            tournament = await uow.tournaments.get_active()
            if tournament is None:
                raise NoActiveTournamentError()
            return list(await uow.matches.list_awaiting_result(tournament.id, self._now()))

    async def set_result(self, match_id: int, result: Outcome | str) -> ResultSummary:
        """Вносит или исправляет результат (в том числе у ранее отменённого матча)."""
        result = parse_outcome(result)
        async with self._uow() as uow:
            match = await self._get_editable_match(uow, match_id)
            if self._now() < match.starts_at:
                raise MatchNotStartedError()
            await uow.matches.set_result(match_id, result)
            counts = await uow.predictions.count_by_outcome(match_id)
            await uow.commit()
            return ResultSummary(match, result, sum(counts.values()), counts.get(result, 0))

    async def cancel_match(self, match_id: int) -> Match:
        """Отмена/перенос: прогнозы на матч не приносят баллов. Можно и до начала."""
        async with self._uow() as uow:
            match = await self._get_editable_match(uow, match_id)
            await uow.matches.cancel(match_id)
            await uow.commit()
            return match

    @staticmethod
    async def _get_editable_match(uow: UnitOfWork, match_id: int) -> Match:
        match = await uow.matches.get_with_round(match_id)
        if match is None:
            raise MatchNotFoundError()
        tournament = await uow.tournaments.get(match.round.tournament_id)
        # Архивный рейтинг заморожен снимком — правка результата его бы не изменила.
        if tournament is None or tournament.status != TournamentStatus.ACTIVE:
            raise TournamentArchivedError()
        return match
