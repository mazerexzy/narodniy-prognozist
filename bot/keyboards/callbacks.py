"""Фабрики CallbackData. Длина упакованной строки не должна превышать 64 байта."""

from __future__ import annotations

from enum import StrEnum

from aiogram.filters.callback_data import CallbackData

from bot.database.models import Outcome


class NoopCB(CallbackData, prefix="noop"):
    """Кнопка-подпись: нажатие ничего не делает."""


class NavTarget(StrEnum):
    ROUNDS = "rounds"


class NavCB(CallbackData, prefix="nav"):
    to: NavTarget


class RoundCB(CallbackData, prefix="rnd"):
    round_id: int


class BetCB(CallbackData, prefix="bet"):
    round_id: int      # чтобы перерисовать экран тура после ставки
    match_id: int
    outcome: Outcome


class LeaderboardCB(CallbackData, prefix="lb"):
    tournament_id: int = 0   # 0 — текущий турнир, иначе id архивного
    page: int = 1


class ArchiveCB(CallbackData, prefix="arc"):
    page: int = 1


# ---------------------------------------------------------------- админка


class AdminAction(StrEnum):
    MENU = "menu"
    CANCEL = "cancel"
    UPLOAD = "upload"
    ADD = "add"
    RESULTS = "results"
    NEW_TOURNAMENT = "new"
    ARCHIVE = "archive"
    ADMINS = "admins"
    DELETE_MATCH = "del_match"
    ADD_ADMIN = "add_admin"


class AdminCB(CallbackData, prefix="adm"):
    action: AdminAction


class ArchiveTournamentCB(CallbackData, prefix="admarc"):
    """Подтверждение архивации конкретного турнира (защита от старых кнопок)."""

    tournament_id: int
    force: bool = False   # True — архивировать, даже если есть матчи без результата


class DeleteMatchRoundCB(CallbackData, prefix="dmr"):
    """Выбран тур, из которого удаляем матч."""

    round_id: int


class DeleteMatchCB(CallbackData, prefix="dm"):
    """confirm=False — экран подтверждения, True — удалить."""

    match_id: int
    confirm: bool = False


class RemoveAdminCB(CallbackData, prefix="admdel"):
    admin_id: int


class AdminRoundCB(CallbackData, prefix="admr"):
    round_id: int


CANCEL_MATCH = "C"


class ResultCB(CallbackData, prefix="res"):
    match_id: int
    result: str    # "1" / "X" / "2" или CANCEL_MATCH
