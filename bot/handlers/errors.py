"""Глобальная обработка ошибок.

ServiceError — ожидаемая ситуация (ник занят, приём закрыт…): показываем её
текст пользователю. FSM-состояние не трогаем, поэтому человек может просто
прислать исправленный ввод. Всё остальное — баг: пишем в лог с трейсбеком, а
пользователю отвечаем нейтральным сообщением, чтобы бот не «молчал».
"""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import ExceptionTypeFilter
from aiogram.types import CallbackQuery, ErrorEvent, Message

from bot.middlewares.cleanup import keep_history
from bot.services.errors import ServiceError
from bot.utils import texts

logger = logging.getLogger(__name__)
router = Router(name="errors")


@router.error(ExceptionTypeFilter(ServiceError), F.update.message.as_("message"))
async def service_error_in_message(event: ErrorEvent, message: Message) -> None:
    with keep_history():   # ввод пользователя остаётся на экране — его можно исправить
        await message.answer(texts.service_error(event.exception))


@router.error(ExceptionTypeFilter(ServiceError), F.update.callback_query.as_("callback"))
async def service_error_in_callback(event: ErrorEvent, callback: CallbackQuery) -> None:
    await callback.answer(texts.service_error_alert(event.exception), show_alert=True)


@router.error()
async def unexpected_error(event: ErrorEvent) -> None:
    logger.error("Необработанная ошибка в апдейте %s", event.update.update_id, exc_info=event.exception)
    try:
        if event.update.callback_query:
            await event.update.callback_query.answer(texts.UNEXPECTED_ERROR, show_alert=True)
        elif event.update.message:
            with keep_history():
                await event.update.message.answer(texts.UNEXPECTED_ERROR)
    except Exception:
        logger.warning("Не удалось сообщить пользователю об ошибке", exc_info=True)
