"""Загрузка туров и добавление матчей текстом."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.keyboards import admin as kb
from bot.keyboards.callbacks import AdminAction, AdminCB, AdminRoundCB
from bot.middlewares.cleanup import keep_history
from bot.services import Services
from bot.services.errors import MatchImportError, NoActiveTournamentError, RoundClosedError, RoundNotFoundError
from bot.states.admin import AdminStates
from bot.utils import texts
from bot.utils.messages import show

router = Router(name="admin_matches")


# ---------------------------------------------------------------- новый тур


@router.callback_query(AdminCB.filter(F.action == AdminAction.UPLOAD))
async def ask_round_text(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminStates.round_text)
    await show(callback, texts.ASK_ROUND_TEXT, kb.cancel())
    await callback.answer()


@router.message(AdminStates.round_text, F.text)
async def import_round(message: Message, state: FSMContext, services: Services) -> None:
    try:
        result = await services.match_import.import_round(message.text)
    except MatchImportError as e:
        # Состояние и присланный список сохраняем: админ отправляет исправленный вариант.
        with keep_history():
            await message.answer(texts.import_failed(e), reply_markup=kb.cancel())
        return
    except NoActiveTournamentError:
        await state.clear()
        raise
    await state.clear()
    await message.answer(texts.import_result(result), reply_markup=kb.back())


# ---------------------------------------------------------------- матчи в существующий тур


@router.callback_query(AdminCB.filter(F.action == AdminAction.ADD))
async def pick_round(callback: CallbackQuery, services: Services) -> None:
    rounds = await services.betting.list_open_rounds()
    if not rounds:
        await callback.answer(texts.NO_OPEN_ROUNDS, show_alert=True)
        return
    await show(callback, texts.PICK_ROUND, kb.open_rounds(rounds))
    await callback.answer()


@router.callback_query(AdminRoundCB.filter())
async def ask_matches_text(callback: CallbackQuery, callback_data: AdminRoundCB, state: FSMContext) -> None:
    await state.set_state(AdminStates.add_matches_text)
    await state.update_data(round_id=callback_data.round_id)
    await show(callback, texts.ASK_ADD_MATCHES_TEXT, kb.cancel())
    await callback.answer()


@router.message(AdminStates.add_matches_text, F.text)
async def add_matches(message: Message, state: FSMContext, services: Services) -> None:
    round_id: int = (await state.get_data())["round_id"]
    try:
        result = await services.match_import.add_matches(round_id, message.text)
    except MatchImportError as e:
        with keep_history():
            await message.answer(texts.import_failed(e), reply_markup=kb.cancel())
        return
    except (RoundClosedError, RoundNotFoundError):
        await state.clear()   # в этот тур добавлять уже нельзя — выходим из режима
        raise
    await state.clear()
    await message.answer(texts.import_result(result), reply_markup=kb.back())


@router.message(AdminStates.round_text)
@router.message(AdminStates.add_matches_text)
async def matches_not_text(message: Message) -> None:
    with keep_history():
        await message.answer(texts.SEND_TEXT, reply_markup=kb.cancel())
