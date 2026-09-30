"""Массовая загрузка матчей одним текстовым сообщением.

Формат (время — МСК, год можно не указывать):

    Тур 5                              <- необязательная первая строка-заголовок
    01.10 19:00 Спартак - Зенит
    01.10.2026 21:30 ЦСКА — Локомотив
    02.10 17:00 Динамо vs Краснодар

Загрузка атомарная: если хоть одна строка с ошибкой, не сохраняется ничего,
а админ получает список всех ошибок с номерами строк.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, tzinfo

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.database.models import Match, Round, TournamentStatus, utcnow
from bot.database.repositories import NewMatch
from bot.services.base import BaseService, Clock
from bot.services.errors import (
    ImportLineError,
    MatchImportError,
    NoActiveTournamentError,
    RoundClosedError,
    RoundNotFoundError,
)
from bot.services.tournament import normalize_title
from bot.utils.timezone import DISPLAY_TZ

# Экран тура: 4 кнопки на матч, а Telegram допускает до 100 кнопок в сообщении
# (24 × 4 + кнопка «назад» = 97). По ТЗ в розыгрыше 10–20 матчей — запас есть.
MAX_MATCHES_PER_ROUND = 24
TEAM_MAX_LEN = 64

_LINE_RE = re.compile(
    r"(?P<day>\d{1,2})\.(?P<month>\d{1,2})(?:\.(?P<year>\d{4}|\d{2}))?"
    r"\s+(?P<hour>\d{1,2})[:.](?P<minute>\d{2})"
    r"\s+(?P<teams>.+)"
)
_DATE_PREFIX_RE = re.compile(r"\d{1,2}\.\d{1,2}")
# Разделитель команд обязательно с пробелами: «Нью-Йорк» не разрежется.
_TEAMS_SEPARATOR_RE = re.compile(r"\s+(?:-|–|—|vs\.?)\s+", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class ParsedMatches:
    title: str | None
    matches: list[NewMatch]


@dataclass(frozen=True, slots=True)
class ImportResult:
    round: Round
    matches: list[Match]
    created_round: bool


def parse_matches_text(text: str, *, now: datetime, tz: tzinfo = DISPLAY_TZ) -> ParsedMatches:
    """Чистая функция: текст -> матчи в UTC. Бросает MatchImportError со всеми ошибками."""
    title: str | None = None
    matches: list[NewMatch] = []
    errors: list[ImportLineError] = []
    seen: set[tuple[str, str, datetime]] = set()
    first_content_line = True

    for line_no, raw in enumerate(text.splitlines(), start=1):
        line = " ".join(raw.split())
        if not line:
            continue
        is_first, first_content_line = first_content_line, False

        m = _LINE_RE.fullmatch(line)
        if m is None:
            if is_first and not _DATE_PREFIX_RE.match(line):
                title = line
            else:
                errors.append(ImportLineError(line_no, line, "неверный формат, ожидается «ДД.ММ ЧЧ:ММ Команда1 - Команда2»"))
            continue

        try:
            starts_at = _build_datetime(m, now=now, tz=tz)
        except ValueError:
            errors.append(ImportLineError(line_no, line, "несуществующая дата или время"))
            continue

        teams = _TEAMS_SEPARATOR_RE.split(m["teams"])
        if len(teams) != 2 or not all(t.strip() for t in teams):
            errors.append(ImportLineError(line_no, line, "необходимо указать две команды через « - »"))
            continue
        home, away = (t.strip() for t in teams)

        if home.casefold() == away.casefold():
            reason = "указаны одинаковые команды"
        elif max(len(home), len(away)) > TEAM_MAX_LEN:
            reason = f"название команды длиннее {TEAM_MAX_LEN} символов"
        elif starts_at <= now:
            reason = "время начала матча уже прошло"
        elif (key := (home.casefold(), away.casefold(), starts_at)) in seen:
            reason = "матч указан повторно"
        else:
            seen.add(key)
            matches.append(NewMatch(home, away, starts_at))
            continue
        errors.append(ImportLineError(line_no, line, reason))

    if not matches and not errors:
        errors.append(ImportLineError(0, "", "в сообщении не найдено ни одного матча"))
    if len(matches) > MAX_MATCHES_PER_ROUND:
        errors.append(ImportLineError(0, "", f"в туре может быть не больше {MAX_MATCHES_PER_ROUND} матчей"))
    if errors:
        raise MatchImportError(errors)
    return ParsedMatches(title, matches)


def _build_datetime(m: re.Match[str], *, now: datetime, tz: tzinfo) -> datetime:
    day, month, hour, minute = (int(m[k]) for k in ("day", "month", "hour", "minute"))
    if m["year"]:
        year = int(m["year"])
        year += 2000 if year < 100 else 0
        return datetime(year, month, day, hour, minute, tzinfo=tz).astimezone(UTC)

    # Год не указан: ближайшая такая дата не раньше сегодняшнего дня
    # (в декабре «15.01» — это январь следующего года).
    local_today = now.astimezone(tz).date()
    year = local_today.year
    if (month, day) < (local_today.month, local_today.day):
        year += 1
    return datetime(year, month, day, hour, minute, tzinfo=tz).astimezone(UTC)


class MatchImportService(BaseService):
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        clock: Clock = utcnow,
        tz: tzinfo = DISPLAY_TZ,
    ) -> None:
        super().__init__(session_factory, clock=clock)
        self._tz = tz

    def parse(self, text: str) -> ParsedMatches:
        """Предпросмотр без записи в БД — чтобы показать админу, что будет загружено."""
        return parse_matches_text(text, now=self._now(), tz=self._tz)

    async def import_round(self, text: str, *, title: str | None = None) -> ImportResult:
        """Создаёт новый тур из текста. Дедлайн = старт самого раннего матча.

        Название: аргумент title > первая строка текста > «Тур N».
        """
        parsed = self.parse(text)
        async with self._uow() as uow:
            tournament = await uow.tournaments.get_active()
            if tournament is None:
                raise NoActiveTournamentError()
            raw_title = title if title is not None else parsed.title
            if raw_title is None:
                existing = await uow.rounds.list_by_tournament(tournament.id)
                round_title = f"Тур {len(existing) + 1}"
            else:
                round_title = normalize_title(raw_title)

            deadline = min(m.starts_at for m in parsed.matches)
            round_ = await uow.rounds.create(tournament.id, round_title, deadline)
            matches = await uow.matches.create_many(round_.id, parsed.matches)
            await uow.commit()
            return ImportResult(round_, matches, created_round=True)

    async def add_matches(self, round_id: int, text: str) -> ImportResult:
        """Добавляет матчи в ещё не начавшийся тур. Строка-заголовок игнорируется.

        Если новый матч раньше текущего дедлайна, дедлайн сдвигается на него.
        """
        parsed = self.parse(text)
        now = self._now()
        async with self._uow() as uow:
            round_ = await uow.rounds.get(round_id)
            if round_ is None:
                raise RoundNotFoundError()
            tournament = await uow.tournaments.get(round_.tournament_id)
            if tournament is None or tournament.status != TournamentStatus.ACTIVE:
                raise RoundNotFoundError()
            if not round_.is_open(now):
                raise RoundClosedError()
            existing = len(await uow.matches.list_by_round(round_id))
            if existing + len(parsed.matches) > MAX_MATCHES_PER_ROUND:
                raise MatchImportError([
                    ImportLineError(
                        0, "", f"в туре может быть не больше {MAX_MATCHES_PER_ROUND} матчей, уже есть {existing}"
                    )
                ])

            matches = await uow.matches.create_many(round_id, parsed.matches)
            earliest = min(m.starts_at for m in parsed.matches)
            if earliest < round_.deadline_at:
                await uow.rounds.set_deadline(round_id, earliest)
            await uow.commit()
            return ImportResult(round_, matches, created_round=False)
