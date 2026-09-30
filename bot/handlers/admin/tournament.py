"""Старт турнира и архивация."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.keyboards import admin as kb
from bot.keyboards.callbacks import AdminAction, AdminCB, ArchiveTournamentCB
from bot.middlewares.cleanup import keep_history
from bot.services import Services
from bot.services.errors import NoActiveTournamentError, TournamentAlreadyActiveError, UnsettledMatchesError
from bot.states.admin import AdminStates
from bot.utils import texts
from bot.utils.messages import show

router = Router(name="admin_tournament")


# ---------------------------------------------------------------- новый турнир


@router.callback_query(AdminCB.filter(F.action == AdminAction.NEW_TOURNAMENT))
async def ask_tournament_title(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminStates.new_tournament_title)
    await show(callback, texts.ASK_TOURNAMENT_TITLE, kb.cancel())
    await callback.answer()


@router.message(AdminStates.new_tournament_title, F.text)
async def start_tournament(message: Message, state: FSMContext, services: Services) -> None:
    try:
        tournament = await services.tournament.start_tournament(message.text)
    except TournamentAlreadyActiveError:
        await state.clear()
        raise
    await state.clear()
    await message.answer(texts.tournament_started(tournament), reply_markup=kb.admin_menu(has_active_tournament=True))


@router.message(AdminStates.new_tournament_title)
async def title_not_text(message: Message) -> None:
    with keep_history():
        await message.answer(texts.SEND_TEXT, reply_markup=kb.cancel())


# ---------------------------------------------------------------- архивация
# Шаг 1: экран подтверждения с id турнира в кнопке.
# Шаг 2: архивация; если остались матчи без результата — предупреждение и
#        кнопка с force=True.


@router.callback_query(AdminCB.filter(F.action == AdminAction.ARCHIVE))
async def confirm_archive(callback: CallbackQuery, state: FSMContext, services: Services) -> None:
    await state.clear()
    tournament = await services.tournament.get_active()
    if tournament is None:
        raise NoActiveTournamentError()
    await show(callback, texts.archive_confirm(tournament), kb.archive_confirm(tournament.id))
    await callback.answer()


@router.callback_query(ArchiveTournamentCB.filter())
async def archive(callback: CallbackQuery, callback_data: ArchiveTournamentCB, services: Services) -> None:
    try:
        result = await services.tournament.archive_active(
            tournament_id=callback_data.tournament_id, force=callback_data.force
        )
    except UnsettledMatchesError as e:
        await show(callback, texts.unsettled_warning(e.count), kb.archive_confirm(callback_data.tournament_id, force=True))
        await callback.answer()
        return
    await show(callback, texts.archived(result), kb.admin_menu(has_active_tournament=False))
    await callback.answer()
