from __future__ import annotations

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message


async def show(callback: CallbackQuery, text: str, reply_markup: InlineKeyboardMarkup | None = None) -> None:
    """Показывает экран в сообщении, на кнопку которого нажали.

    Если сообщение нельзя отредактировать (старше 48 ч или недоступно) —
    отправляет новое. Повторное нажатие той же кнопки («message is not
    modified») молча игнорируется.
    """
    message = callback.message
    if isinstance(message, Message):
        try:
            await message.edit_text(text, reply_markup=reply_markup)
            return
        except TelegramBadRequest as e:
            if "message is not modified" in e.message:
                return
            if "message can't be edited" not in e.message and "message to edit not found" not in e.message:
                raise
    await callback.bot.send_message(callback.from_user.id, text, reply_markup=reply_markup)
