from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.database.models import User
from bot.services import Services
from bot.utils import texts

router = Router(name="user_my_bets")


@router.message(F.text == texts.BTN_MY_BETS)
async def my_predictions(message: Message, state: FSMContext, user: User, services: Services) -> None:
    await state.clear()
    views = await services.betting.get_my_predictions(user.telegram_id)
    await message.answer(texts.my_predictions(views))
