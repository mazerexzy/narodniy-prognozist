"""Таблица лидеров текущего турнира и архив прошлых.

Участники видят только ники и баллы. Админам в тех же таблицах показываются
контакты (@username, ссылка на профиль, ID) — ТЗ, п. 1.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.database.models import User
from bot.keyboards import user as kb
from bot.keyboards.callbacks import ArchiveCB, LeaderboardCB
from bot.services import Services
from bot.utils import texts
from bot.utils.messages import show

router = Router(name="user_leaderboard")


@router.message(F.text == texts.BTN_LEADERBOARD)
async def current_leaderboard(
    message: Message, state: FSMContext, user: User, services: Services, is_admin: bool
) -> None:
    await state.clear()
    page = await services.leaderboard.get_current(viewer_id=user.telegram_id)
    await message.answer(
        texts.leaderboard(page, archived=False, show_contacts=is_admin),
        reply_markup=kb.leaderboard(page, archived=False),
    )


@router.callback_query(LeaderboardCB.filter())
async def leaderboard_page(
    callback: CallbackQuery,
    callback_data: LeaderboardCB,
    user: User,
    services: Services,
    is_admin: bool,
) -> None:
    archived = callback_data.tournament_id != 0
    if archived:
        page = await services.leaderboard.get_archived(
            callback_data.tournament_id, page=callback_data.page, viewer_id=user.telegram_id
        )
    else:
        page = await services.leaderboard.get_current(page=callback_data.page, viewer_id=user.telegram_id)
    await show(
        callback,
        texts.leaderboard(page, archived=archived, show_contacts=is_admin),
        kb.leaderboard(page, archived=archived),
    )
    await callback.answer()


@router.message(F.text == texts.BTN_ARCHIVE)
async def archive(message: Message, state: FSMContext, services: Services) -> None:
    await state.clear()
    page = await services.leaderboard.list_archived()
    await message.answer(texts.archive_list(page), reply_markup=kb.archive_list(page))


@router.callback_query(ArchiveCB.filter())
async def archive_page(callback: CallbackQuery, callback_data: ArchiveCB, services: Services) -> None:
    page = await services.leaderboard.list_archived(page=callback_data.page)
    await show(callback, texts.archive_list(page), kb.archive_list(page))
    await callback.answer()
