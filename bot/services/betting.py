from __future__ import annotations

from dataclasses import dataclass

from bot.database.models import Match, MatchStatus, Outcome, Prediction, Round, TournamentStatus
from bot.database.repositories import UnitOfWork
from bot.services.base import BaseService
from bot.services.errors import (
    BettingClosedError,
    MatchNotFoundError,
    NoActiveTournamentError,
    NotRegisteredError,
    RoundNotFoundError,
    UserBannedError,
)
from bot.services.scoring import PredictionState, evaluate, parse_outcome


@dataclass(frozen=True, slots=True)
class RoundSummary:
    round: Round
    is_open: bool


@dataclass(frozen=True, slots=True)
class RoundView:
    """Тур глазами конкретного участника."""

    round: Round
    matches: list[Match]
    my_outcomes: dict[int, Outcome]   # match_id -> выбранный исход
    is_open: bool


@dataclass(frozen=True, slots=True)
class PredictionView:
    prediction: Prediction
    match: Match
    state: PredictionState


class BettingService(BaseService):
    async def list_rounds(self) -> list[RoundSummary]:
        """Все туры активного турнира: открытые и уже закрытые."""
        now = self._now()
        async with self._uow() as uow:
            tournament = await uow.tournaments.get_active()
            if tournament is None:
                raise NoActiveTournamentError()
            rounds = await uow.rounds.list_by_tournament(tournament.id)
            return [RoundSummary(r, r.is_open(now)) for r in rounds]

    async def list_open_rounds(self) -> list[Round]:
        async with self._uow() as uow:
            tournament = await uow.tournaments.get_active()
            if tournament is None:
                raise NoActiveTournamentError()
            return list(await uow.rounds.list_open(tournament.id, self._now()))

    async def get_round(self, user_id: int, round_id: int) -> RoundView:
        async with self._uow() as uow:
            round_ = await uow.rounds.get_with_matches(round_id)
            if round_ is None or not await self._is_active_tournament(uow, round_.tournament_id):
                raise RoundNotFoundError()
            return RoundView(
                round=round_,
                matches=list(round_.matches),
                my_outcomes=await uow.predictions.get_outcomes_for_round(user_id, round_id),
                is_open=round_.is_open(self._now()),
            )

    async def place_bet(self, user_id: int, match_id: int, outcome: Outcome | str) -> Prediction:
        """Принимает или меняет прогноз.

        Дедлайн проверяется здесь, по серверному времени, на каждый запрос:
        кнопки старого сообщения в Telegram могут быть нажаты когда угодно.
        """
        outcome = parse_outcome(outcome)
        now = self._now()
        async with self._uow() as uow:
            user = await uow.users.get(user_id)
            if user is None:
                raise NotRegisteredError()
            if user.is_banned:
                raise UserBannedError()

            match = await uow.matches.get_with_round(match_id)
            if match is None:
                raise MatchNotFoundError()
            if (
                not await self._is_active_tournament(uow, match.round.tournament_id)
                or match.status != MatchStatus.SCHEDULED
                or now >= match.round.deadline_at
                or now >= match.starts_at
            ):
                raise BettingClosedError()

            prediction = await uow.predictions.upsert(user_id, match_id, outcome)
            await uow.commit()
            return prediction

    async def get_my_predictions(self, user_id: int) -> list[PredictionView]:
        """Прогнозы участника в активном турнире со статусом «угадал/нет»."""
        async with self._uow() as uow:
            tournament = await uow.tournaments.get_active()
            if tournament is None:
                raise NoActiveTournamentError()
            predictions = await uow.predictions.list_by_user(user_id, tournament.id)
            return [PredictionView(p, p.match, evaluate(p.outcome, p.match)) for p in predictions]

    @staticmethod
    async def _is_active_tournament(uow: UnitOfWork, tournament_id: int) -> bool:
        tournament = await uow.tournaments.get(tournament_id)
        return tournament is not None and tournament.status == TournamentStatus.ACTIVE
