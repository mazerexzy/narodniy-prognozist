"""Удаление отдельного матча из тура."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from bot.database.models import Match, MatchStatus, Round, TournamentStatus
from bot.database.repositories import UnitOfWork
from bot.services.base import BaseService
from bot.services.errors import MatchNotFoundError, RoundNotFoundError, TournamentArchivedError


@dataclass(frozen=True, slots=True)
class MatchDeletePreview:
    """Что будет удалено — для экрана подтверждения."""

    match: Match
    round: Round
    predictions: int          # прогнозы на матч удалятся вместе с ним
    matches_in_round: int

    @property
    def has_result(self) -> bool:
        return self.match.status == MatchStatus.FINISHED

    @property
    def is_last_in_round(self) -> bool:
        return self.matches_in_round == 1


@dataclass(frozen=True, slots=True)
class MatchDeleteResult:
    match: Match
    round: Round
    round_deleted: bool               # в туре не осталось матчей — тур удалён
    new_deadline: datetime | None     # дедлайн открытого тура сдвинулся


class MatchAdminService(BaseService):
    async def list_round_matches(self, round_id: int) -> tuple[Round, list[Match]]:
        async with self._uow() as uow:
            round_ = await uow.rounds.get_with_matches(round_id)
            if round_ is None or not await _is_active(uow, round_.tournament_id):
                raise RoundNotFoundError()
            return round_, list(round_.matches)

    async def preview_delete(self, match_id: int) -> MatchDeletePreview:
        async with self._uow() as uow:
            match = await _get_editable_match(uow, match_id)
            counts = await uow.predictions.count_by_outcome(match_id)
            matches_in_round = len(await uow.matches.list_by_round(match.round_id))
            return MatchDeletePreview(match, match.round, sum(counts.values()), matches_in_round)

    async def delete_match(self, match_id: int) -> MatchDeleteResult:
        """Удаляет матч вместе с прогнозами на него.

        Дедлайн тура = старт первого матча, поэтому:
        - тур ещё открыт → дедлайн пересчитывается по оставшимся матчам;
        - тур уже закрыт → дедлайн не трогаем (закрытый приём не открываем заново);
        - матчей не осталось → удаляем пустой тур.
        """
        now = self._now()
        async with self._uow() as uow:
            match = await _get_editable_match(uow, match_id)
            round_ = match.round
            was_open = round_.is_open(now)

            await uow.matches.delete(match_id)
            earliest = await uow.matches.get_earliest_start(round_.id)

            round_deleted, new_deadline = False, None
            if earliest is None:
                await uow.rounds.delete(round_.id)
                round_deleted = True
            elif was_open and earliest != round_.deadline_at:
                await uow.rounds.set_deadline(round_.id, earliest)
                new_deadline = earliest

            await uow.commit()
            return MatchDeleteResult(match, round_, round_deleted, new_deadline)


async def _is_active(uow: UnitOfWork, tournament_id: int) -> bool:
    tournament = await uow.tournaments.get(tournament_id)
    return tournament is not None and tournament.status == TournamentStatus.ACTIVE


async def _get_editable_match(uow: UnitOfWork, match_id: int) -> Match:
    match = await uow.matches.get_with_round(match_id)
    if match is None:
        raise MatchNotFoundError()
    if not await _is_active(uow, match.round.tournament_id):
        raise TournamentArchivedError()
    return match
