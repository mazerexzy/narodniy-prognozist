"""Доменные ошибки сервисов.

Хэндлер ловит `ServiceError` и показывает пользователю понятное сообщение.
Текст по умолчанию годится для логов и как запасной вариант ответа, а
пользовательские формулировки можно держать в utils/texts.py по типу ошибки.
"""

from __future__ import annotations

from dataclasses import dataclass


class ServiceError(Exception):
    """Базовая ошибка бизнес-логики (ожидаемая, не баг)."""


# ---------------------------------------------------------------- пользователи


class InvalidNicknameError(ServiceError):
    pass


class NicknameTakenError(ServiceError):
    def __init__(self, nickname: str) -> None:
        super().__init__(f"Ник «{nickname}» уже занят. Укажите другой.")
        self.nickname = nickname


class AlreadyRegisteredError(ServiceError):
    def __init__(self) -> None:
        super().__init__("Вы уже зарегистрированы.")


class NotRegisteredError(ServiceError):
    def __init__(self) -> None:
        super().__init__("Необходима регистрация. Отправьте /start.")


class UserBannedError(ServiceError):
    def __init__(self) -> None:
        super().__init__("Доступ к турниру ограничен.")


# ---------------------------------------------------------------- турниры


class NoActiveTournamentError(ServiceError):
    def __init__(self) -> None:
        super().__init__("Активный турнир отсутствует.")


class TournamentAlreadyActiveError(ServiceError):
    def __init__(self) -> None:
        super().__init__("Активный турнир уже существует. Сначала переместите его в архив.")


class TournamentNotFoundError(ServiceError):
    def __init__(self) -> None:
        super().__init__("Турнир не найден.")


class TournamentArchivedError(ServiceError):
    def __init__(self) -> None:
        super().__init__("Турнир находится в архиве, изменения недоступны.")


class InvalidTitleError(ServiceError):
    pass


class UnsettledMatchesError(ServiceError):
    """Архивация остановлена: не по всем матчам внесён результат."""

    def __init__(self, count: int) -> None:
        super().__init__(f"Матчей без результата: {count}.")
        self.count = count


# ---------------------------------------------------------------- туры и матчи


class RoundNotFoundError(ServiceError):
    def __init__(self) -> None:
        super().__init__("Тур не найден.")


class RoundClosedError(ServiceError):
    def __init__(self) -> None:
        super().__init__("Тур уже начался, добавление матчей недоступно.")


class MatchNotFoundError(ServiceError):
    def __init__(self) -> None:
        super().__init__("Матч не найден.")


class MatchNotStartedError(ServiceError):
    def __init__(self) -> None:
        super().__init__("Матч ещё не начался, внесение результата недоступно.")


# ---------------------------------------------------------------- ставки


class InvalidOutcomeError(ServiceError):
    def __init__(self, value: object) -> None:
        super().__init__(f"Неизвестный исход: {value!r}.")


class BettingClosedError(ServiceError):
    def __init__(self) -> None:
        super().__init__("Приём прогнозов на этот матч закрыт.")


# ---------------------------------------------------------------- импорт матчей


@dataclass(frozen=True, slots=True)
class ImportLineError:
    line_no: int   # номер строки в сообщении админа, с 1; 0 — ошибка всего списка
    line: str
    reason: str


class MatchImportError(ServiceError):
    """Загрузка отклонена целиком: ни один матч не сохранён."""

    def __init__(self, errors: list[ImportLineError]) -> None:
        details = "\n".join(
            f"Строка {e.line_no}: {e.reason} — «{e.line}»" if e.line_no else f"Весь список: {e.reason}"
            for e in errors
        )
        super().__init__(f"Матчи не загружены. Исправьте ошибки:\n{details}")
        self.errors = errors


# ---------------------------------------------------------------- администраторы


class InvalidUsernameError(ServiceError):
    def __init__(self) -> None:
        super().__init__(
            "Укажите username в формате @username: 5–32 символа, латинские буквы, цифры и подчёркивание."
        )


class AlreadyAdminError(ServiceError):
    def __init__(self, username: str) -> None:
        super().__init__(f"@{username} уже является администратором.")
        self.username = username


class AdminNotFoundError(ServiceError):
    def __init__(self) -> None:
        super().__init__("Администратор не найден или уже удалён.")
