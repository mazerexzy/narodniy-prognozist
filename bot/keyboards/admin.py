from __future__ import annotations

from collections.abc import Sequence

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.database.models import Match, Outcome, Round
from bot.keyboards.callbacks import (
    CANCEL_MATCH,
    AdminAction,
    AdminCB,
    AdminRoundCB,
    ArchiveTournamentCB,
    DeleteMatchCB,
    DeleteMatchRoundCB,
    NoopCB,
    RemoveAdminCB,
    ResultCB,
)
from bot.keyboards.user import button
from bot.services.admins import AdminList
from bot.utils import texts
from bot.utils.timezone import fmt_datetime

BACK = button("⬅️ Админка", AdminCB(action=AdminAction.MENU))


def admin_menu(*, has_active_tournament: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if has_active_tournament:
        builder.row(button("📥 Загрузить тур", AdminCB(action=AdminAction.UPLOAD)))
        builder.row(button("➕ Добавить матчи в тур", AdminCB(action=AdminAction.ADD)))
        builder.row(button("🗑 Удалить матч", AdminCB(action=AdminAction.DELETE_MATCH)))
        builder.row(button("📝 Внести результаты", AdminCB(action=AdminAction.RESULTS)))
        builder.row(button("🗄 Архивировать турнир", AdminCB(action=AdminAction.ARCHIVE)))
    else:
        builder.row(button("🚀 Начать турнир", AdminCB(action=AdminAction.NEW_TOURNAMENT)))
    builder.row(button("👥 Администраторы", AdminCB(action=AdminAction.ADMINS)))
    return builder.as_markup()


def admins(admin_list: AdminList) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(button("➕ Добавить администратора", AdminCB(action=AdminAction.ADD_ADMIN)))
    for a in admin_list.bot_admins:
        label = f"@{a.username}" if a.username else (a.nickname or f"ID {a.telegram_id}")
        builder.row(button(f"❌ Удалить {label}", RemoveAdminCB(admin_id=a.admin_id)))
    builder.row(BACK)
    return builder.as_markup()


def back() -> InlineKeyboardMarkup:
    return InlineKeyboardBuilder().row(BACK).as_markup()


def cancel() -> InlineKeyboardMarkup:
    return InlineKeyboardBuilder().row(button("✖️ Отмена", AdminCB(action=AdminAction.CANCEL))).as_markup()


def open_rounds(rounds: Sequence[Round]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for r in rounds:
        builder.row(button(f"{r.title} · {fmt_datetime(r.deadline_at)}", AdminRoundCB(round_id=r.id)))
    builder.row(BACK)
    return builder.as_markup()


def awaiting_results(matches: Sequence[Match]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for i, match in enumerate(matches, start=1):
        builder.row(button(texts.match_button(i, match), NoopCB()))
        builder.row(
            *(button(texts.OUTCOME_LABELS[o], ResultCB(match_id=match.id, result=o.value)) for o in Outcome),
            button("❌", ResultCB(match_id=match.id, result=CANCEL_MATCH)),
        )
    builder.row(BACK)
    return builder.as_markup()


def delete_pick_round(rounds: Sequence[Round]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for r in rounds:
        builder.row(button(f"{r.title} · {fmt_datetime(r.deadline_at)}", DeleteMatchRoundCB(round_id=r.id)))
    builder.row(BACK)
    return builder.as_markup()


def delete_pick_match(matches: Sequence[Match]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for i, match in enumerate(matches, start=1):
        builder.row(button(
            f"🗑 {texts.match_button(i, match)} · {fmt_datetime(match.starts_at)}", DeleteMatchCB(match_id=match.id)
        ))
    builder.row(button("⬅️ К турам", AdminCB(action=AdminAction.DELETE_MATCH)))
    builder.row(BACK)
    return builder.as_markup()


def delete_confirm(match: Match) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(button("🗑 Удалить", DeleteMatchCB(match_id=match.id, confirm=True)))
    builder.row(button("⬅️ Назад", DeleteMatchRoundCB(round_id=match.round_id)))
    return builder.as_markup()


def archive_confirm(tournament_id: int, *, force: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(button("🗄 Архивировать", ArchiveTournamentCB(tournament_id=tournament_id, force=force)))
    builder.row(button("✖️ Отмена", AdminCB(action=AdminAction.MENU)))
    return builder.as_markup()
