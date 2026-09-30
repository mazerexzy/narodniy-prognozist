"""Правило начисления баллов.

Очки в БД не хранятся: их считает SQL-запрос LeaderboardRepository._standings
по тому же правилу, что описано здесь. Меняете правило — меняйте в обоих местах.
"""

from __future__ import annotations

from enum import StrEnum

from bot.database.models import Match, MatchStatus, Outcome
from bot.services.errors import InvalidOutcomeError

POINTS_PER_HIT = 1


class PredictionState(StrEnum):
    PENDING = "pending"   # результата ещё нет
    HIT = "hit"           # угадал
    MISS = "miss"         # не угадал
    VOID = "void"         # матч отменён, баллы не начисляются


def evaluate(outcome: Outcome, match: Match) -> PredictionState:
    if match.status == MatchStatus.CANCELLED:
        return PredictionState.VOID
    if match.status != MatchStatus.FINISHED or match.result is None:
        return PredictionState.PENDING
    return PredictionState.HIT if outcome == match.result else PredictionState.MISS


def points_for(state: PredictionState) -> int:
    return POINTS_PER_HIT if state == PredictionState.HIT else 0


def parse_outcome(value: Outcome | str) -> Outcome:
    """Принимает Outcome или строку "1"/"X"/"2" (также "х" кириллицей и "x")."""
    if isinstance(value, Outcome):
        return value
    normalized = str(value).strip().upper().replace("Х", "X")
    try:
        return Outcome(normalized)
    except ValueError:
        raise InvalidOutcomeError(value) from None

