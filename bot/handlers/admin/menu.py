from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.keyboards import admin as kb
from bot.keyboards.callbacks import AdminAction, AdminCB
from bot.services import Services
from bot.utils import texts
from bot.utils.messages import show

router = Router(name="admin_menu")


@router.message(F.text == texts.BTN_ADMIN)
@router.message(Command("admin"))
async def admin_menu(message: Message, state: FSMContext, services: Services) -> None:
    await state.clear()
    tournament = await services.tournament.get_active()
    users_count = await services.registration.count_users()
    await message.answer(
        texts.admin_menu(tournament, users_count),
        reply_markup=kb.admin_menu(has_active_tournament=tournament is not None),
    )


@router.callback_query(AdminCB.filter(F.action == AdminAction.MENU))
async def back_to_menu(callback: CallbackQuery, state: FSMContext, services: Services) -> None:
    await state.clear()
    tournament = await services.tournament.get_active()
    users_count = await services.registration.count_users()
    await show(
        callback,
        texts.admin_menu(tournament, users_count),
        kb.admin_menu(has_active_tournament=tournament is not None),
    )
    await callback.answer()


@router.callback_query(AdminCB.filter(F.action == AdminAction.CANCEL))
async def cancel(callback: CallbackQuery, state: FSMContext, services: Services) -> None:
    # Отмена возвращает в панель, а не оставляет «тупиковое» сообщение.
    await back_to_menu(callback, state, services)
