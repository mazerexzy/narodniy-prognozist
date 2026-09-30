"""Внесение результатов и отмена матчей."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup

from bot.keyboards import admin as kb
from bot.keyboards.callbacks import CANCEL_MATCH, AdminAction, AdminCB, ResultCB
from bot.services import Services
from bot.utils import texts
from bot.utils.messages import show

router = Router(name="admin_results")

# 5 кнопок на матч + «назад»: укладываемся в лимит Telegram 100 кнопок.
MATCHES_PER_SCREEN = 15


@router.callback_query(AdminCB.filter(F.action == AdminAction.RESULTS))
async def awaiting_results(callback: CallbackQuery, services: Services) -> None:
    text, markup = await _screen(services)
    await show(callback, text, markup)
    await callback.answer()


@router.callback_query(ResultCB.filter())
async def set_result(callback: CallbackQuery, callback_data: ResultCB, services: Services) -> None:
    if callback_data.result == CANCEL_MATCH:
        match = await services.results.cancel_match(callback_data.match_id)
        note = texts.match_cancelled(match)
    else:
        summary = await services.results.set_result(callback_data.match_id, callback_data.result)
        note = texts.result_saved(summary)
    text, markup = await _screen(services)
    await show(callback, text, markup)
    await callback.answer(note, show_alert=True)


async def _screen(services: Services) -> tuple[str, InlineKeyboardMarkup]:
    matches = await services.results.list_awaiting_results()
    shown = matches[:MATCHES_PER_SCREEN]
    return texts.awaiting_results(shown, total=len(matches)), kb.awaiting_results(shown)
