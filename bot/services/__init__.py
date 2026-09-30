"""Бизнес-логика. Ничего не знает про aiogram: принимает данные, возвращает
результат или бросает ServiceError."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.database.models import utcnow
from bot.services.admins import AdminService
from bot.services.base import Clock
from bot.services.betting import BettingService
from bot.services.leaderboard import LeaderboardService
from bot.services.match_admin import MatchAdminService
from bot.services.match_import import MatchImportService
from bot.services.registration import RegistrationService
from bot.services.results import ResultsService
from bot.services.tournament import TournamentService


@dataclass(frozen=True, slots=True)
class Services:
    """Все сервисы разом — создаётся один раз при старте и кладётся в Dispatcher."""

    registration: RegistrationService
    betting: BettingService
    results: ResultsService
    leaderboard: LeaderboardService
    tournament: TournamentService
    match_import: MatchImportService
    match_admin: MatchAdminService
    admins: AdminService

    @classmethod
    def create(
        cls,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        admin_ids: Iterable[int] = (),
        clock: Clock = utcnow,
    ) -> Services:
        return cls(
            registration=RegistrationService(session_factory, clock=clock),
            betting=BettingService(session_factory, clock=clock),
            results=ResultsService(session_factory, clock=clock),
            leaderboard=LeaderboardService(session_factory, clock=clock),
            tournament=TournamentService(session_factory, clock=clock),
            match_import=MatchImportService(session_factory, clock=clock),
            match_admin=MatchAdminService(session_factory, clock=clock),
            admins=AdminService(session_factory, config_admin_ids=admin_ids, clock=clock),
        )


__all__ = [
    "AdminService",
    "BettingService",
    "LeaderboardService",
    "MatchAdminService",
    "MatchImportService",
    "RegistrationService",
    "ResultsService",
    "Services",
    "TournamentService",
]
