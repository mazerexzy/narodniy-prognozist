"""Удаление отдельного матча: тур → матч → подтверждение."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot.keyboards import admin as kb
from bot.keyboards.callbacks import AdminAction, AdminCB, DeleteMatchCB, DeleteMatchRoundCB
from bot.services import Services
from bot.utils import texts
from bot.utils.messages import show

router = Router(name="admin_delete_match")


@router.callback_query(AdminCB.filter(F.action == AdminAction.DELETE_MATCH))
async def pick_round(callback: CallbackQuery, services: Services) -> None:
    await _show_rounds(callback, services)
    await callback.answer()


@router.callback_query(DeleteMatchRoundCB.filter())
async def pick_match(callback: CallbackQuery, callback_data: DeleteMatchRoundCB, services: Services) -> None:
    await _show_round_matches(callback, services, callback_data.round_id)
    await callback.answer()


@router.callback_query(DeleteMatchCB.filter(~F.confirm))
async def confirm(callback: CallbackQuery, callback_data: DeleteMatchCB, services: Services) -> None:
    preview = await services.match_admin.preview_delete(callback_data.match_id)
    await show(callback, texts.delete_confirm(preview), kb.delete_confirm(preview.match))
    await callback.answer()


@router.callback_query(DeleteMatchCB.filter(F.confirm))
async def delete(callback: CallbackQuery, callback_data: DeleteMatchCB, services: Services) -> None:
    result = await services.match_admin.delete_match(callback_data.match_id)
    if result.round_deleted:
        await _show_rounds(callback, services)
    else:
        await _show_round_matches(callback, services, result.round.id)
    await callback.answer(texts.match_deleted(result), show_alert=True)


async def _show_rounds(callback: CallbackQuery, services: Services) -> None:
    rounds = [s.round for s in await services.betting.list_rounds()]
    if not rounds:
        await show(callback, texts.NO_ROUNDS_TO_DELETE, kb.back())
        return
    await show(callback, texts.PICK_ROUND_TO_DELETE, kb.delete_pick_round(rounds))


async def _show_round_matches(callback: CallbackQuery, services: Services, round_id: int) -> None:
    round_, matches = await services.match_admin.list_round_matches(round_id)
    await show(callback, texts.delete_pick_match(round_), kb.delete_pick_match(matches))
