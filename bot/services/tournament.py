from __future__ import annotations

from dataclasses import dataclass

from bot.database.models import Tournament
from bot.database.repositories import UnitOfWork
from bot.services.base import BaseService
from bot.services.errors import (
    InvalidTitleError,
    NoActiveTournamentError,
    TournamentAlreadyActiveError,
    TournamentArchivedError,
    UnsettledMatchesError,
)

TITLE_MAX_LEN = 128


@dataclass(frozen=True, slots=True)
class ArchiveResult:
    archived: Tournament
    participants: int                 # строк в замороженной таблице
    new_tournament: Tournament | None


def normalize_title(raw: str) -> str:
    title = " ".join(raw.split())
    if not title:
        raise InvalidTitleError("Название не может быть пустым.")
    if len(title) > TITLE_MAX_LEN:
        raise InvalidTitleError(f"Название не должно превышать {TITLE_MAX_LEN} символов.")
    return title


class TournamentService(BaseService):
    async def get_active(self) -> Tournament | None:
        async with self._uow() as uow:
            return await uow.tournaments.get_active()

    async def start_tournament(self, raw_title: str) -> Tournament:
        title = normalize_title(raw_title)
        async with self._uow() as uow:
            tournament = await uow.tournaments.create(title)
            if tournament is None:
                raise TournamentAlreadyActiveError()
            await uow.commit()
            return tournament

    async def archive_active(self, *, tournament_id: int | None = None, force: bool = False) -> ArchiveResult:
        """Замораживает рейтинг и отправляет активный турнир в архив.

        Без force отказывает, если остались матчи без результата/отмены: иначе
        прогнозы на них пропадут из итоговой таблицы. Хэндлер показывает админу
        UnsettledMatchesError.count и переспрашивает с force=True.

        tournament_id — какой турнир админ видел на экране подтверждения. Если
        активен уже другой (кнопку нажали в старом сообщении), архивации не будет.
        """
        async with self._uow() as uow:
            result = await self._archive(uow, force=force, expected_id=tournament_id)
            await uow.commit()
            return result

    async def archive_and_start_new(self, raw_new_title: str, *, force: bool = False) -> ArchiveResult:
        """Архивация + новый турнир одной транзакцией: либо всё, либо ничего."""
        title = normalize_title(raw_new_title)
        async with self._uow() as uow:
            result = await self._archive(uow, force=force)
            new_tournament = await uow.tournaments.create(title)
            assert new_tournament is not None  # активный только что заархивирован
            await uow.commit()
            return ArchiveResult(result.archived, result.participants, new_tournament)

    async def _archive(self, uow: UnitOfWork, *, force: bool, expected_id: int | None = None) -> ArchiveResult:
        tournament = await uow.tournaments.get_active()
        if expected_id is not None and (tournament is None or tournament.id != expected_id):
            raise TournamentArchivedError()
        if tournament is None:
            raise NoActiveTournamentError()
        if not force and (unsettled := await uow.matches.count_unsettled(tournament.id)):
            raise UnsettledMatchesError(unsettled)
        participants = await uow.leaderboard.save_snapshot(tournament.id)
        # ORM-UPDATE синхронизирует объект в сессии: tournament.status уже ARCHIVED.
        await uow.tournaments.archive(tournament.id, self._now())
        return ArchiveResult(tournament, participants, None)
