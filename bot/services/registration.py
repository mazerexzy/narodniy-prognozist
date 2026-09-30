from __future__ import annotations

import re

from bot.database.models import User
from bot.services.base import BaseService
from bot.services.errors import (
    AlreadyRegisteredError,
    InvalidNicknameError,
    NicknameTakenError,
    NotRegisteredError,
)
from bot.services.profanity import is_profane

NICKNAME_MIN_LEN = 3
NICKNAME_MAX_LEN = 20
_NICKNAME_RE = re.compile(r"[\w .\-]+")  # буквы любого алфавита, цифры, _ пробел . -


def normalize_nickname(raw: str) -> str:
    """Чистит ник от лишних пробелов и проверяет формат. Возвращает готовый ник."""
    nickname = " ".join(raw.split())
    if not NICKNAME_MIN_LEN <= len(nickname) <= NICKNAME_MAX_LEN:
        raise InvalidNicknameError(f"Ник должен содержать от {NICKNAME_MIN_LEN} до {NICKNAME_MAX_LEN} символов.")
    if not _NICKNAME_RE.fullmatch(nickname):
        raise InvalidNicknameError("В нике допускаются только буквы, цифры, пробел и символы _ . -")
    if not any(ch.isalpha() for ch in nickname):
        raise InvalidNicknameError("Ник должен содержать хотя бы одну букву.")
    if is_profane(nickname):
        raise InvalidNicknameError("Ник содержит недопустимые выражения. Выберите другой ник.")
    return nickname


_KEEP = object()   # «username не передан — не трогать»


class RegistrationService(BaseService):
    async def get_user(self, telegram_id: int, tg_username: str | None | object = _KEEP) -> User | None:
        """Находит пользователя. Если передан tg_username (в т.ч. None — username
        удалён в Telegram), синхронизирует его; без аргумента — только чтение.

        Запись в БД происходит только при реальном изменении — метод можно
        вызывать на каждом апдейте из middleware.
        """
        async with self._uow() as uow:
            user = await uow.users.get(telegram_id)
            if user is not None and tg_username is not _KEEP and user.tg_username != tg_username:
                await uow.users.update_tg_username(telegram_id, tg_username)
                user.tg_username = tg_username
                await uow.commit()
            return user

    async def count_users(self) -> int:
        async with self._uow() as uow:
            return await uow.users.count()

    async def is_nickname_available(self, raw_nickname: str) -> bool:
        """Для подсказки в диалоге. Окончательная проверка всё равно в register()."""
        nickname = normalize_nickname(raw_nickname)
        async with self._uow() as uow:
            return not await uow.users.is_nickname_taken(nickname)

    async def register(self, telegram_id: int, raw_nickname: str, tg_username: str | None = None) -> User:
        nickname = normalize_nickname(raw_nickname)
        async with self._uow() as uow:
            if await uow.users.get(telegram_id) is not None:
                raise AlreadyRegisteredError()
            user = await uow.users.create(telegram_id, nickname, tg_username)
            if user is None:
                # Конфликт: либо ник занят, либо параллельный /start того же человека.
                if await uow.users.get(telegram_id) is not None:
                    raise AlreadyRegisteredError()
                raise NicknameTakenError(nickname)
            await uow.commit()
            return user

    async def change_nickname(self, telegram_id: int, raw_nickname: str) -> User:
        nickname = normalize_nickname(raw_nickname)
        async with self._uow() as uow:
            user = await uow.users.get(telegram_id)
            if user is None:
                raise NotRegisteredError()
            if user.nickname == nickname:
                return user
            if not await uow.users.update_nickname(telegram_id, nickname):
                raise NicknameTakenError(nickname)
            await uow.commit()
            return user
