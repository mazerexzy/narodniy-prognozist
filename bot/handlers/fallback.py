"""Подключается последним: ловит всё, что не подошло ни одному хэндлеру."""

from __future__ import annotations

from aiogram import Router
from aiogram.types import CallbackQuery, Message

from bot.keyboards.callbacks import NoopCB
from bot.middlewares.cleanup import keep_history
from bot.utils import texts

router = Router(name="fallback")


@router.callback_query(NoopCB.filter())
async def noop(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query()
async def stale_button(callback: CallbackQuery) -> None:
    await callback.answer(texts.STALE_BUTTON)


@router.message()
async def unknown_message(message: Message) -> None:
    # Не стираем текущий экран из-за случайного сообщения.
    with keep_history():
        await message.answer(texts.UNKNOWN_INPUT)
