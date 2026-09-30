from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.enums import ChatType
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove, TelegramObject
from aiogram.types import User as TgUser

from bot.middlewares.cleanup import keep_history
from bot.services import Services
from bot.services.profanity import is_profane
from bot.states.registration import Profile, Registration
from bot.utils import texts

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


class AuthMiddleware(BaseMiddleware):
    """Пропускает к хэндлерам только зарегистрированных пользователей.

    - в data всегда кладётся `is_admin` (права проверяются на каждый апдейт,
      поэтому выданные/снятые через бот права действуют сразу);
    - зарегистрирован → в data кладётся `user` (ORM-модель User);
    - забанен → вежливый отказ, хэндлер не вызывается;
    - ник недопустим (зарегистрирован до появления фильтра) → принудительная
      смена ника: до хэндлеров доходит только сообщение с новым ником;
    - не зарегистрирован → FSM переводится в Registration.nickname и бот
      просит ник. Дальше до хэндлеров доходят только сообщения с ником.

    Вешается как outer-middleware на message и callback_query, поэтому
    срабатывает до фильтров хэндлеров.
    """

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        tg_user: TgUser | None = data.get("event_from_user")
        if tg_user is None or tg_user.is_bot or not _is_private(event):
            return None  # бот работает только в личке

        services: Services = data["services"]
        data["is_admin"] = await services.admins.is_admin(tg_user.id, tg_user.username)
        user = await services.registration.get_user(tg_user.id, tg_user.username)

        if user is not None:
            if user.is_banned:
                await _reply(event, texts.BANNED, alert=True)
                return None
            data["user"] = user
            if is_profane(user.nickname):
                return await _force_rename(handler, event, data)
            return await handler(event, data)

        state: FSMContext = data["state"]
        if await state.get_state() == Registration.nickname.state:
            if isinstance(event, Message):
                return await handler(event, data)   # это ответ с ником — пропускаем
            await _reply(event, texts.FINISH_REGISTRATION_ALERT, alert=True)
            return None

        await state.set_state(Registration.nickname)
        await _reply(event, texts.ASK_NICKNAME)
        return None


async def _force_rename(handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
    state: FSMContext = data["state"]
    if await state.get_state() == Profile.new_nickname.state and isinstance(event, Message):
        text = event.text or ""
        if text and not text.startswith("/") and text not in texts.MENU_BUTTONS:
            return await handler(event, data)   # новый ник — в хэндлер смены ника
    if isinstance(event, CallbackQuery):
        await event.answer(texts.FORCE_RENAME_ALERT, show_alert=True)
    else:
        await state.set_state(Profile.new_nickname)
        with keep_history():
            await _reply(event, texts.FORCE_RENAME)
    return None


def _is_private(event: TelegramObject) -> bool:
    if isinstance(event, Message):
        return event.chat.type == ChatType.PRIVATE
    if isinstance(event, CallbackQuery):
        return event.message is None or event.message.chat.type == ChatType.PRIVATE
    return True


async def _reply(event: TelegramObject, text: str, *, alert: bool = False) -> None:
    if isinstance(event, Message):
        await event.answer(text, reply_markup=ReplyKeyboardRemove())
    elif isinstance(event, CallbackQuery):
        if alert:
            await event.answer(text, show_alert=True)
            return
        await event.answer()
        await event.bot.send_message(event.from_user.id, text, reply_markup=ReplyKeyboardRemove())
