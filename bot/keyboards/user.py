from __future__ import annotations

from collections.abc import Callable, Sequence

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.database.models import MatchStatus, Outcome
from bot.keyboards.callbacks import ArchiveCB, BetCB, LeaderboardCB, NavCB, NavTarget, NoopCB, RoundCB
from bot.services.betting import RoundSummary, RoundView
from bot.services.leaderboard import ArchivePage, LeaderboardPage
from bot.utils import texts

CLOSED_ROUNDS_SHOWN = 5


def button(text: str, callback_data: CallbackData) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=callback_data.pack())


def main_menu(*, is_admin: bool) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text=texts.BTN_MATCHES), KeyboardButton(text=texts.BTN_MY_BETS)],
        [KeyboardButton(text=texts.BTN_LEADERBOARD), KeyboardButton(text=texts.BTN_ARCHIVE)],
        [KeyboardButton(text=texts.BTN_NICKNAME)],
    ]
    if is_admin:
        rows[-1].append(KeyboardButton(text=texts.BTN_ADMIN))
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=True)


def pager(builder: InlineKeyboardBuilder, page: int, pages: int, make: Callable[[int], CallbackData]) -> None:
    if pages <= 1:
        return
    row = []
    if page > 1:
        row.append(button("◀️", make(page - 1)))
    row.append(button(f"{page} / {pages}", NoopCB()))
    if page < pages:
        row.append(button("▶️", make(page + 1)))
    builder.row(*row)


def rounds_list(summaries: Sequence[RoundSummary]) -> InlineKeyboardMarkup | None:
    """Открытые туры (ближайшие сверху) и несколько последних закрытых."""
    opened = [s for s in summaries if s.is_open]
    closed = [s for s in summaries if not s.is_open][-CLOSED_ROUNDS_SHOWN:][::-1]
    if not opened and not closed:
        return None
    builder = InlineKeyboardBuilder()
    for s in (*opened, *closed):
        builder.row(button(texts.round_button(s), RoundCB(round_id=s.round.id)))
    return builder.as_markup()


def round_view(view: RoundView) -> InlineKeyboardMarkup:
    """Под каждым матчем — строка П1 / Х / П2, выбранный исход отмечен ✅."""
    builder = InlineKeyboardBuilder()
    if view.is_open:
        for i, match in enumerate(view.matches, start=1):
            builder.row(button(texts.match_button(i, match), NoopCB()))
            if match.status != MatchStatus.SCHEDULED:
                continue
            chosen = view.my_outcomes.get(match.id)
            builder.row(*(
                button(
                    ("✅ " if outcome == chosen else "") + texts.OUTCOME_LABELS[outcome],
                    BetCB(round_id=view.round.id, match_id=match.id, outcome=outcome),
                )
                for outcome in Outcome
            ))
    builder.row(button("⬅️ К турам", NavCB(to=NavTarget.ROUNDS)))
    return builder.as_markup()


def leaderboard(page: LeaderboardPage, *, archived: bool) -> InlineKeyboardMarkup | None:
    tournament_id = page.tournament.id if archived else 0
    builder = InlineKeyboardBuilder()
    pager(builder, page.page, page.pages, lambda p: LeaderboardCB(tournament_id=tournament_id, page=p))
    if archived:
        builder.row(button("⬅️ К архиву", ArchiveCB(page=1)))
    return builder.as_markup() if builder.buttons else None


def archive_list(page: ArchivePage) -> InlineKeyboardMarkup | None:
    if not page.tournaments:
        return None
    builder = InlineKeyboardBuilder()
    for t in page.tournaments:
        builder.row(button(texts.archive_button(t), LeaderboardCB(tournament_id=t.id, page=1)))
    pager(builder, page.page, page.pages, lambda p: ArchiveCB(page=p))
    return builder.as_markup()
