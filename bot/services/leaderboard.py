from __future__ import annotations

from dataclasses import dataclass
from math import ceil

from bot.database.models import Tournament, TournamentStatus
from bot.database.repositories import Standing
from bot.services.base import BaseService
from bot.services.errors import NoActiveTournamentError, TournamentNotFoundError

LEADERBOARD_PAGE_SIZE = 20
ARCHIVE_PAGE_SIZE = 10


@dataclass(frozen=True, slots=True)
class LeaderboardPage:
    tournament: Tournament
    rows: list[Standing]
    page: int
    pages: int
    total: int                    # участников в рейтинге
    viewer: Standing | None       # строка того, кто смотрит (даже если он не на этой странице)


@dataclass(frozen=True, slots=True)
class ArchivePage:
    tournaments: list[Tournament]
    page: int
    pages: int
    total: int


def _paginate(total: int, page: int, page_size: int) -> tuple[int, int, int]:
    """(страница, всего страниц, offset). Номер страницы с 1, выход за границы обрезается."""
    pages = max(1, ceil(total / page_size))
    page = min(max(1, page), pages)
    return page, pages, (page - 1) * page_size


class LeaderboardService(BaseService):
    async def get_current(
        self, *, page: int = 1, viewer_id: int | None = None, page_size: int = LEADERBOARD_PAGE_SIZE
    ) -> LeaderboardPage:
        async with self._uow() as uow:
            tournament = await uow.tournaments.get_active()
            if tournament is None:
                raise NoActiveTournamentError()
            total = await uow.leaderboard.count_participants(tournament.id)
            page, pages, offset = _paginate(total, page, page_size)
            rows = await uow.leaderboard.get_standings(tournament.id, limit=page_size, offset=offset)
            viewer = (
                await uow.leaderboard.get_user_standing(tournament.id, viewer_id) if viewer_id else None
            )
            return LeaderboardPage(tournament, rows, page, pages, total, viewer)

    async def list_archived(self, *, page: int = 1, page_size: int = ARCHIVE_PAGE_SIZE) -> ArchivePage:
        async with self._uow() as uow:
            total = await uow.tournaments.count_archived()
            page, pages, offset = _paginate(total, page, page_size)
            tournaments = await uow.tournaments.list_archived(limit=page_size, offset=offset)
            return ArchivePage(list(tournaments), page, pages, total)

    async def get_archived(
        self,
        tournament_id: int,
        *,
        page: int = 1,
        viewer_id: int | None = None,
        page_size: int = LEADERBOARD_PAGE_SIZE,
    ) -> LeaderboardPage:
        async with self._uow() as uow:
            tournament = await uow.tournaments.get(tournament_id)
            if tournament is None or tournament.status != TournamentStatus.ARCHIVED:
                raise TournamentNotFoundError()
            total = await uow.leaderboard.count_snapshot(tournament_id)
            page, pages, offset = _paginate(total, page, page_size)
            rows = await uow.leaderboard.get_snapshot(tournament_id, limit=page_size, offset=offset)
            viewer = (
                await uow.leaderboard.get_snapshot_entry(tournament_id, viewer_id) if viewer_id else None
            )
            return LeaderboardPage(tournament, rows, page, pages, total, viewer)
