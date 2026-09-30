"""Управление администраторами: любой админ может добавлять и удалять назначенных через бот."""

from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.keyboards import admin as kb
from bot.keyboards.callbacks import AdminAction, AdminCB, RemoveAdminCB
from bot.keyboards.user import main_menu
from bot.middlewares.cleanup import keep_history
from bot.services import Services
from bot.states.admin import AdminStates
from bot.utils import texts
from bot.utils.messages import show

logger = logging.getLogger(__name__)
router = Router(name="admin_admins")


@router.callback_query(AdminCB.filter(F.action == AdminAction.ADMINS))
async def admins_list(callback: CallbackQuery, state: FSMContext, services: Services) -> None:
    await state.clear()
    admin_list = await services.admins.list_admins()
    await show(callback, texts.admins_screen(admin_list), kb.admins(admin_list))
    await callback.answer()


@router.callback_query(AdminCB.filter(F.action == AdminAction.ADD_ADMIN))
async def ask_username(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminStates.new_admin_username)
    await show(callback, texts.ASK_ADMIN_USERNAME, kb.cancel())
    await callback.answer()


@router.message(AdminStates.new_admin_username, F.text)
async def add_admin(message: Message, state: FSMContext, services: Services, bot: Bot) -> None:
    # InvalidUsernameError / AlreadyAdminError уходят в глобальный обработчик, состояние сохраняется.
    added = await services.admins.add_admin(message.from_user.id, message.text)
    await state.clear()
    if added.telegram_id is not None:
        await _notify(bot, added.telegram_id, texts.ADMIN_GRANTED, is_admin=True)
    admin_list = await services.admins.list_admins()
    await message.answer(
        f"{texts.admin_added(added)}\n\n{texts.admins_screen(admin_list)}", reply_markup=kb.admins(admin_list)
    )


@router.message(AdminStates.new_admin_username)
async def username_not_text(message: Message) -> None:
    with keep_history():
        await message.answer(texts.SEND_TEXT, reply_markup=kb.cancel())


@router.callback_query(RemoveAdminCB.filter())
async def remove_admin(callback: CallbackQuery, callback_data: RemoveAdminCB, services: Services, bot: Bot) -> None:
    removed = await services.admins.remove_admin(callback_data.admin_id)
    if removed.telegram_id is not None:
        await _notify(bot, removed.telegram_id, texts.ADMIN_REVOKED, is_admin=False)
    admin_list = await services.admins.list_admins()
    await show(callback, texts.admins_screen(admin_list), kb.admins(admin_list))
    await callback.answer(texts.admin_removed(removed), show_alert=True)


async def _notify(bot: Bot, telegram_id: int, text: str, *, is_admin: bool) -> None:
    """Сообщает человеку об изменении прав и обновляет его нижнее меню."""
    try:
        await bot.send_message(telegram_id, text, reply_markup=main_menu(is_admin=is_admin))
    except Exception:
        # Например, пользователь заблокировал бота — права всё равно изменены.
        logger.warning("Не удалось уведомить пользователя %s об изменении прав", telegram_id, exc_info=True)
