"""Регистрация, /start, /help, /cancel, смена ника."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.database.models import User
from bot.handlers.user.matches import send_matches_screen
from bot.keyboards.user import main_menu
from bot.middlewares.cleanup import keep_history
from bot.services import Services
from bot.services.errors import AlreadyRegisteredError, NoActiveTournamentError
from bot.states.registration import Profile, Registration
from bot.utils import texts

router = Router(name="user_start")


# ---------------------------------------------------------------- регистрация
# Сюда доходят только незарегистрированные: AuthMiddleware уже перевёл их в
# Registration.nickname. Порядок хэндлеров важен: команды — раньше ника.


@router.message(Registration.nickname, F.text.startswith("/"))
async def registration_command(message: Message) -> None:
    with keep_history():
        await message.answer(texts.FINISH_REGISTRATION)


@router.message(Registration.nickname, F.text)
async def registration_nickname(
    message: Message, state: FSMContext, services: Services, is_admin: bool
) -> None:
    tg_user = message.from_user
    try:
        user = await services.registration.register(tg_user.id, message.text, tg_user.username)
    except AlreadyRegisteredError:
        user = await services.registration.get_user(tg_user.id, tg_user.username)
    # InvalidNicknameError / NicknameTakenError уходят в глобальный обработчик,
    # состояние остаётся — человек просто присылает другой ник.
    await state.clear()
    await message.answer(texts.registered(user), reply_markup=main_menu(is_admin=is_admin))
    await _show_matches_after_start(message, services, user)


@router.message(Registration.nickname)
async def registration_not_text(message: Message) -> None:
    with keep_history():
        await message.answer(texts.SEND_TEXT)


# ---------------------------------------------------------------- команды


@router.message(CommandStart())
@router.message(Command("menu"))
async def start(
    message: Message, state: FSMContext, user: User, services: Services, is_admin: bool
) -> None:
    await state.clear()
    await message.answer(texts.main_menu(user), reply_markup=main_menu(is_admin=is_admin))
    await _show_matches_after_start(message, services, user)


async def _show_matches_after_start(message: Message, services: Services, user: User) -> None:
    """ТЗ, п. 2: после регистрации и /start сразу показываем матчи."""
    try:
        await send_matches_screen(message, services, user.telegram_id)
    except NoActiveTournamentError:
        await message.answer(texts.NO_ACTIVE_TOURNAMENT)


@router.message(Command("help"))
async def help_(message: Message) -> None:
    await message.answer(texts.HELP)


@router.message(Command("cancel"))
async def cancel(message: Message, state: FSMContext) -> None:
    had_state = await state.get_state() is not None
    await state.clear()
    await message.answer(texts.CANCELLED if had_state else texts.NOTHING_TO_CANCEL)


# ---------------------------------------------------------------- смена ника


@router.message(F.text == texts.BTN_NICKNAME)
async def ask_new_nickname(message: Message, state: FSMContext) -> None:
    await state.set_state(Profile.new_nickname)
    await message.answer(texts.ASK_NEW_NICKNAME)


# Кнопки меню не считаем ником: они уходят в свои хэндлеры и сбрасывают состояние.
@router.message(Profile.new_nickname, F.text, ~F.text.in_(texts.MENU_BUTTONS))
async def change_nickname(message: Message, state: FSMContext, user: User, services: Services) -> None:
    updated = await services.registration.change_nickname(user.telegram_id, message.text)
    await state.clear()
    await message.answer(texts.nickname_changed(updated))


@router.message(Profile.new_nickname, ~F.text)
async def change_nickname_not_text(message: Message) -> None:
    with keep_history():
        await message.answer(texts.SEND_TEXT)
