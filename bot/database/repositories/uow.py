from __future__ import annotations

from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.database.repositories.admins import AdminRepository
from bot.database.repositories.leaderboard import LeaderboardRepository
from bot.database.repositories.matches import MatchRepository
from bot.database.repositories.predictions import PredictionRepository
from bot.database.repositories.rounds import RoundRepository
from bot.database.repositories.tournaments import TournamentRepository
from bot.database.repositories.users import UserRepository


class UnitOfWork:
    """Единственная точка доступа сервисов к БД.

    Одна сессия и одна транзакция на весь блок `async with`. Изменения
    сохраняются только явным `await uow.commit()`; выход из блока без commit
    (в том числе по исключению) откатывает всё.

        async with UnitOfWork(session_factory) as uow:
            user = await uow.users.get(tg_id)
            ...
            await uow.commit()
    """

    users: UserRepository
    tournaments: TournamentRepository
    admins: AdminRepository
    rounds: RoundRepository
    matches: MatchRepository
    predictions: PredictionRepository
    leaderboard: LeaderboardRepository

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> UnitOfWork:
        if self._session is not None:
            raise RuntimeError("UnitOfWork уже открыт")
        session = self._session = self._session_factory()
        self.users = UserRepository(session)
        self.tournaments = TournamentRepository(session)
        self.admins = AdminRepository(session)
        self.rounds = RoundRepository(session)
        self.matches = MatchRepository(session)
        self.predictions = PredictionRepository(session)
        self.leaderboard = LeaderboardRepository(session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        assert self._session is not None
        # close() откатывает незакоммиченную транзакцию, но, в отличие от
        # rollback(), не «протухает» загруженные объекты: их можно вернуть из
        # сервиса и читать после выхода из блока.
        try:
            await self._session.close()
        finally:
            self._session = None

    async def commit(self) -> None:
        assert self._session is not None, "UnitOfWork используется вне async with"
        await self._session.commit()

    async def rollback(self) -> None:
        assert self._session is not None, "UnitOfWork используется вне async with"
        await self._session.rollback()
