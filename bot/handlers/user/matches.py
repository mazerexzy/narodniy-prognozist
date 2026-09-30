"""Список туров, экран тура и приём прогнозов."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.database.models import User
from bot.keyboards import user as kb
from bot.keyboards.callbacks import BetCB, NavCB, NavTarget, RoundCB
from bot.services import Services
from bot.services.errors import BettingClosedError
from bot.utils import texts
from bot.utils.messages import show

router = Router(name="user_matches")


@router.message(F.text == texts.BTN_MATCHES)
async def matches(message: Message, state: FSMContext, user: User, services: Services) -> None:
    await state.clear()
    await send_matches_screen(message, services, user.telegram_id)


async def send_matches_screen(message: Message, services: Services, user_id: int) -> None:
    """Экран матчей (ТЗ, п. 2). Если открыт ровно один тур — сразу его матчи
    с кнопками П1/Х/П2, иначе список туров.

    Бросает NoActiveTournamentError, если турнир не начат.
    """
    summaries = await services.betting.list_rounds()
    opened = [s for s in summaries if s.is_open]
    if len(opened) == 1:
        view = await services.betting.get_round(user_id, opened[0].round.id)
        await message.answer(texts.round_view(view), reply_markup=kb.round_view(view))
    else:
        await message.answer(texts.rounds_list(summaries), reply_markup=kb.rounds_list(summaries))


@router.callback_query(NavCB.filter(F.to == NavTarget.ROUNDS))
async def back_to_rounds(callback: CallbackQuery, services: Services) -> None:
    summaries = await services.betting.list_rounds()
    await show(callback, texts.rounds_list(summaries), kb.rounds_list(summaries))
    await callback.answer()


@router.callback_query(RoundCB.filter())
async def open_round(callback: CallbackQuery, callback_data: RoundCB, user: User, services: Services) -> None:
    await _show_round(callback, services, user.telegram_id, callback_data.round_id)
    await callback.answer()


@router.callback_query(BetCB.filter())
async def place_bet(callback: CallbackQuery, callback_data: BetCB, user: User, services: Services) -> None:
    try:
        await services.betting.place_bet(user.telegram_id, callback_data.match_id, callback_data.outcome)
    except BettingClosedError as e:
        # Кнопки в сообщении устарели — перерисуем тур уже без них.
        await _show_round(callback, services, user.telegram_id, callback_data.round_id)
        await callback.answer(str(e), show_alert=True)
        return
    await _show_round(callback, services, user.telegram_id, callback_data.round_id)
    await callback.answer(texts.bet_accepted(callback_data.outcome))


async def _show_round(callback: CallbackQuery, services: Services, user_id: int, round_id: int) -> None:
    view = await services.betting.get_round(user_id, round_id)
    await show(callback, texts.round_view(view), kb.round_view(view))
