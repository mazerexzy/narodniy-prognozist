"""Все тексты бота и форматирование сообщений (parse_mode = HTML).

Стиль — официальный: без разговорных оборотов и эмодзи-эмоций. Значки
оставлены только как функциональные обозначения (статусы, разделы меню).

Любую строку, пришедшую от людей (ники, команды, названия), выводим через q().
Тексты для callback.answer() и кнопок — обычные строки, их экранировать не нужно.
"""

from __future__ import annotations

from collections.abc import Sequence
from html import escape

from bot.database.models import Match, MatchStatus, Outcome, Round, Tournament, User
from bot.database.repositories import Standing
from bot.services.admins import AdminList, AdminView
from bot.services.betting import PredictionView, RoundSummary, RoundView
from bot.services.errors import MatchImportError
from bot.services.leaderboard import ArchivePage, LeaderboardPage
from bot.services.match_admin import MatchDeletePreview, MatchDeleteResult
from bot.services.match_import import ImportResult
from bot.services.profanity import is_profane
from bot.services.registration import NICKNAME_MAX_LEN, NICKNAME_MIN_LEN
from bot.services.results import ResultSummary
from bot.services.scoring import PredictionState, evaluate, points_for
from bot.services.tournament import ArchiveResult
from bot.utils.timezone import fmt_date, fmt_datetime

MESSAGE_LIMIT = 4096
ALERT_LIMIT = 200
MY_PREDICTIONS_LIMIT = 30

# ---------------------------------------------------------------- кнопки меню

BTN_MATCHES = "⚽ Матчи"
BTN_MY_BETS = "📋 Мои прогнозы"
BTN_LEADERBOARD = "🏆 Рейтинг"
BTN_ARCHIVE = "📚 Архив"
BTN_NICKNAME = "✏️ Сменить ник"
BTN_ADMIN = "🛠 Админка"
MENU_BUTTONS = frozenset({BTN_MATCHES, BTN_MY_BETS, BTN_LEADERBOARD, BTN_ARCHIVE, BTN_NICKNAME, BTN_ADMIN})

OUTCOME_LABELS = {Outcome.HOME: "П1", Outcome.DRAW: "Х", Outcome.AWAY: "П2"}
STATE_ICONS = {
    PredictionState.PENDING: "⏳",
    PredictionState.HIT: "✅",
    PredictionState.MISS: "❌",
    PredictionState.VOID: "➖",
}
MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}


# ---------------------------------------------------------------- помощники


def q(text: str) -> str:
    return escape(text, quote=False)


def truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def plural(n: int, forms: tuple[str, str, str]) -> str:
    """plural(5, ("балл", "балла", "баллов")) -> "баллов"."""
    n = abs(n) % 100
    if 10 < n < 20:
        return forms[2]
    if n % 10 == 1:
        return forms[0]
    if 2 <= n % 10 <= 4:
        return forms[1]
    return forms[2]


def points(n: int) -> str:
    return f"{n} {plural(n, ('балл', 'балла', 'баллов'))}"


def matches_count(n: int) -> str:
    return f"{n} {plural(n, ('матч', 'матча', 'матчей'))}"


def match_title(match: Match) -> str:
    return q(f"{match.home_team} — {match.away_team}")


# ---------------------------------------------------------------- общее

ASK_NICKNAME = (
    "<b>«Народный прогнозист»</b> — турнир прогнозов на спортивные матчи.\n\n"
    "Участники прогнозируют исходы матчей: П1 — победа первой команды, Х — ничья, "
    "П2 — победа второй команды. За каждый верный прогноз начисляется 1 балл.\n\n"
    f"Для участия укажите ник ({NICKNAME_MIN_LEN}–{NICKNAME_MAX_LEN} символов). "
    "Он будет отображаться в таблице лидеров."
)
FINISH_REGISTRATION = "Для продолжения завершите регистрацию: отправьте ник одним сообщением."
FINISH_REGISTRATION_ALERT = "Сначала завершите регистрацию: отправьте ник сообщением."
SEND_TEXT = "Отправьте, пожалуйста, текстовое сообщение."
ASK_NEW_NICKNAME = (
    f"Введите новый ник ({NICKNAME_MIN_LEN}–{NICKNAME_MAX_LEN} символов). Для отмены отправьте /cancel."
)
CANCELLED = "Действие отменено."
NOTHING_TO_CANCEL = "Нет активного действия для отмены."
UNKNOWN_INPUT = "Команда не распознана. Воспользуйтесь кнопками меню."
STALE_BUTTON = "Кнопка больше не действительна."
UNEXPECTED_ERROR = "Произошла техническая ошибка. Повторите попытку позже."
BANNED = "Доступ к турниру ограничен."
TOO_FAST = "Слишком частые запросы. Подождите секунду."
HELP = (
    "<b>Правила</b>\n\n"
    f"1. В разделе «{BTN_MATCHES}» выберите тур и укажите исход каждого матча: "
    "П1 — победа первой команды, Х — ничья, П2 — победа второй команды.\n"
    "2. Прогнозы принимаются и могут быть изменены до начала первого матча тура.\n"
    "3. За каждый верный прогноз начисляется 1 балл. Отменённые матчи не учитываются.\n"
    f"4. Таблица лидеров — в разделе «{BTN_LEADERBOARD}», "
    f"итоги завершённых турниров — в разделе «{BTN_ARCHIVE}».\n\n"
    "Время указано по Москве."
)


FORCE_RENAME = (
    "Ваш текущий ник не соответствует правилам участия. "
    f"Придумайте новый ник ({NICKNAME_MIN_LEN}–{NICKNAME_MAX_LEN} символов) и отправьте его сообщением — "
    "без этого продолжить нельзя."
)
FORCE_RENAME_ALERT = "Сначала смените ник: отправьте новый ник сообщением."
HIDDEN_NICKNAME = "Участник (ник скрыт)"


def public_nickname(nickname: str) -> str:
    """Ник для показа другим участникам: недопустимые ники скрываются."""
    return HIDDEN_NICKNAME if is_profane(nickname) else nickname


def registered(user: User) -> str:
    return f"Регистрация завершена. Ваш ник: <b>{q(user.nickname)}</b>."


NO_ACTIVE_TOURNAMENT = "Приём прогнозов пока не открыт. Следите за анонсами."


def main_menu(user: User) -> str:
    return f"<b>Главное меню</b>\nВаш ник: <b>{q(user.nickname)}</b>"


def nickname_changed(user: User) -> str:
    return f"Ник изменён. Новый ник: <b>{q(user.nickname)}</b>."


def service_error(error: Exception) -> str:
    return q(truncate(str(error), MESSAGE_LIMIT - 10))


def service_error_alert(error: Exception) -> str:
    return truncate(str(error), ALERT_LIMIT)


# ---------------------------------------------------------------- туры и прогнозы


def rounds_list(summaries: Sequence[RoundSummary]) -> str:
    if not summaries:
        return "Туры пока не опубликованы."
    return "<b>Туры</b>\n🟢 — приём прогнозов открыт\n🔒 — приём прогнозов закрыт"


def round_button(summary: RoundSummary) -> str:
    icon = "🟢" if summary.is_open else "🔒"
    return f"{icon} {summary.round.title} · {fmt_datetime(summary.round.deadline_at)}"


def round_view(view: RoundView) -> str:
    round_ = view.round
    lines = [f"<b>{q(round_.title)}</b>"]
    if view.is_open:
        made = sum(1 for m in view.matches if m.id in view.my_outcomes)
        lines.append(f"🟢 Приём прогнозов до <b>{fmt_datetime(round_.deadline_at)}</b> (МСК)")
        lines.append(f"Сделано прогнозов: {made} из {len(view.matches)}")
    else:
        lines.append("🔒 Приём прогнозов закрыт")
    lines.append("")

    for i, match in enumerate(view.matches, start=1):
        lines.append(f"{i}. {match_title(match)} · {fmt_datetime(match.starts_at)}")
        mine = view.my_outcomes.get(match.id)
        details = f"Ваш прогноз: <b>{OUTCOME_LABELS[mine]}</b>" if mine else "Ваш прогноз: —"
        if match.status == MatchStatus.CANCELLED:
            details += " · матч отменён ➖"
        elif match.result is not None:
            icon = STATE_ICONS[evaluate(mine, match)] if mine else ""
            details += f" · результат: <b>{OUTCOME_LABELS[match.result]}</b> {icon}"
        lines.append(f"    {details}")
    return "\n".join(lines).rstrip()


def match_button(index: int, match: Match) -> str:
    suffix = " (отменён)" if match.status == MatchStatus.CANCELLED else ""
    return f"{index}. {match.home_team} — {match.away_team}{suffix}"


def bet_accepted(outcome: Outcome) -> str:
    return f"Прогноз принят: {OUTCOME_LABELS[outcome]}"


def my_predictions(views: Sequence[PredictionView]) -> str:
    if not views:
        return f"В текущем турнире у вас пока нет прогнозов. Прогнозы принимаются в разделе «{BTN_MATCHES}»."
    settled = [v for v in views if v.state in (PredictionState.HIT, PredictionState.MISS)]
    hits = sum(1 for v in settled if v.state == PredictionState.HIT)
    total_points = sum(points_for(v.state) for v in views)
    lines = [
        "<b>Мои прогнозы</b>",
        f"Верных прогнозов: {hits} из {len(settled)} по завершённым матчам · {points(total_points)}",
        "",
    ]
    for v in views[:MY_PREDICTIONS_LIMIT]:
        line = (
            f"{STATE_ICONS[v.state]} {match_title(v.match)} ({fmt_datetime(v.match.starts_at)}): "
            f"<b>{OUTCOME_LABELS[v.prediction.outcome]}</b>"
        )
        if v.state in (PredictionState.HIT, PredictionState.MISS) and v.match.result is not None:
            line += f", результат {OUTCOME_LABELS[v.match.result]}"
        lines.append(line)
    if len(views) > MY_PREDICTIONS_LIMIT:
        lines.append(f"… и ещё {len(views) - MY_PREDICTIONS_LIMIT}")
    return "\n".join(lines)


# ---------------------------------------------------------------- рейтинг


def contact(standing: Standing) -> str:
    """Данные аккаунта участника — только для админов (ТЗ, п. 1)."""
    username = f"@{q(standing.tg_username)}" if standing.tg_username else "без username"
    return (
        f'{username} · <a href="tg://user?id={standing.user_id}">профиль</a> · '
        f"ID <code>{standing.user_id}</code>"
    )


def leaderboard(page: LeaderboardPage, *, archived: bool, show_contacts: bool = False) -> str:
    header = f"🏆 <b>{q(page.tournament.title)}</b>" + (" · архив" if archived else "")
    if not page.rows:
        return f"{header}\n\nУчастники в рейтинге пока отсутствуют."

    lines = [header]
    if show_contacts:
        lines.append("<i>Контакты участников видны только администраторам.</i>")
    lines.append("")
    viewer_id = page.viewer.user_id if page.viewer else None
    for s in page.rows:
        row = f"{MEDALS.get(s.place, f'{s.place}.')} {q(public_nickname(s.nickname))} — {points(s.points)}"
        lines.append(f"<b>{row}</b> (вы)" if s.user_id == viewer_id else row)
        if show_contacts:
            lines.append(f"      {contact(s)}")

    lines.append("")
    if page.viewer:
        lines.append(
            f"Ваше место: <b>{page.viewer.place}</b> из {page.total} · {points(page.viewer.points)}"
        )
    elif not archived:
        lines.append("Вы появитесь в рейтинге после первого прогноза.")
    return "\n".join(lines).rstrip()


def archive_list(page: ArchivePage) -> str:
    if page.total == 0:
        return "Архив пуст: завершённых турниров пока нет."
    return "📚 <b>Архив турниров</b>\nВыберите турнир для просмотра итоговой таблицы."


def archive_button(tournament: Tournament) -> str:
    finished = f" · {fmt_date(tournament.archived_at)}" if tournament.archived_at else ""
    return f"{tournament.title}{finished}"


# ---------------------------------------------------------------- админка


def admin_menu(tournament: Tournament | None, users_count: int) -> str:
    lines = ["<b>Панель администратора</b>", ""]
    if tournament is None:
        lines.append("Активный турнир отсутствует. Для загрузки туров начните новый турнир.")
    else:
        lines.append(f"Активный турнир: <b>{q(tournament.title)}</b>")
    lines.append(f"Зарегистрировано участников: {users_count}")
    lines.append(f"\nКонтакты участников отображаются в разделах «{BTN_LEADERBOARD}» и «{BTN_ARCHIVE}».")
    return "\n".join(lines)


ASK_ROUND_TEXT = (
    "Отправьте список матчей одним сообщением, по одному матчу в строке. "
    "Время указывается по Москве, год — по желанию:\n\n"
    "<code>Тур 5\n"
    "01.10 19:00 Спартак - Зенит\n"
    "01.10 21:30 ЦСКА - Локомотив</code>\n\n"
    "Первая строка с названием тура необязательна. "
    "Приём прогнозов закрывается с началом первого матча тура."
)
ASK_ADD_MATCHES_TEXT = (
    "Отправьте матчи для добавления в тур в том же формате, по одному матчу в строке:\n\n"
    "<code>02.10 17:00 Динамо - Краснодар</code>"
)
PICK_ROUND = "Выберите тур для добавления матчей:"
NO_OPEN_ROUNDS = "Нет туров, приём прогнозов по которым ещё открыт."
ASK_TOURNAMENT_TITLE = "Введите название нового турнира:"


def import_result(result: ImportResult) -> str:
    action = "создан" if result.created_round else "дополнен"
    lines = [
        f"Тур «<b>{q(result.round.title)}</b>» {action}: {matches_count(len(result.matches))}.",
        f"Приём прогнозов до <b>{fmt_datetime(result.round.deadline_at)}</b> (МСК).",
        "",
    ]
    lines += [f"• {match_title(m)} · {fmt_datetime(m.starts_at)}" for m in result.matches]
    return "\n".join(lines)


def import_failed(error: MatchImportError) -> str:
    return (
        f"{q(truncate(str(error), MESSAGE_LIMIT - 200))}\n\n"
        "Отправьте исправленный список целиком или нажмите «Отмена»."
    )


def awaiting_results(matches: Sequence[Match], total: int) -> str:
    if not matches:
        return "Все начавшиеся матчи обработаны."
    lines = ["<b>Матчи без результата</b>", "Укажите результат; ❌ — матч отменён.", ""]
    lines += [f"{i}. {match_title(m)} · {fmt_datetime(m.starts_at)}" for i, m in enumerate(matches, 1)]
    if total > len(matches):
        lines.append(f"\n… и ещё {matches_count(total - len(matches))}: будут показаны после обработки текущих.")
    return "\n".join(lines)


def result_saved(summary: ResultSummary) -> str:
    m = summary.match
    return truncate(
        f"{m.home_team} — {m.away_team}: {OUTCOME_LABELS[summary.result]}. "
        f"Верных прогнозов: {summary.hits} из {summary.predictions_total}.",
        ALERT_LIMIT,
    )


def match_cancelled(match: Match) -> str:
    return truncate(f"{match.home_team} — {match.away_team}: матч отменён, баллы не начисляются.", ALERT_LIMIT)


def tournament_started(tournament: Tournament) -> str:
    return f"Турнир «<b>{q(tournament.title)}</b>» начат. Теперь можно загружать туры."


def archive_confirm(tournament: Tournament) -> str:
    return (
        f"Архивировать турнир «<b>{q(tournament.title)}</b>»?\n\n"
        f"Итоговая таблица будет сохранена в разделе «{BTN_ARCHIVE}», "
        "приём прогнозов по турниру будет прекращён. Действие необратимо."
    )


def unsettled_warning(count: int) -> str:
    return (
        f"Внимание: по {count} {plural(count, ('матчу', 'матчам', 'матчам'))} не внесён результат. "
        "Прогнозы на эти матчи не будут учтены в итоговой таблице.\n\n"
        "Архивировать турнир?"
    )


def archived(result: ArchiveResult) -> str:
    n = result.participants
    lines = [
        f"Турнир «<b>{q(result.archived.title)}</b>» перемещён в архив. "
        f"В итоговой таблице {n} {plural(n, ('участник', 'участника', 'участников'))}."
    ]
    if result.new_tournament:
        lines.append(f"Начат новый турнир: «<b>{q(result.new_tournament.title)}</b>».")
    else:
        lines.append("\nЧтобы начать новый турнир, нажмите «Начать турнир».")
    return "\n".join(lines)


# ---------------------------------------------------------------- администраторы


def _admin_label(a: AdminView) -> str:
    return f"@{a.username}" if a.username else (a.nickname or f"ID {a.telegram_id}")


def _admin_line(a: AdminView) -> str:
    parts = []
    if a.nickname:
        parts.append(f"<b>{q(a.nickname)}</b>")
    if a.username:
        parts.append(f"@{q(a.username)}")
    if a.telegram_id:
        parts.append(f"ID <code>{a.telegram_id}</code>")
    else:
        parts.append("<i>ожидает запуска бота</i>")
    return " · ".join(parts)


def admins_screen(admin_list: AdminList) -> str:
    lines = ["<b>Администраторы</b>", "", "Постоянные (заданы в настройках, удалить через бот нельзя):"]
    lines += [f"• {_admin_line(a)}" for a in admin_list.config_admins] or ["—"]
    lines += ["", "Назначенные через бот:"]
    lines += [f"• {_admin_line(a)}" for a in admin_list.bot_admins] or ["—"]
    lines += ["", "Добавлять и удалять назначенных администраторов может любой администратор."]
    return "\n".join(lines)


ASK_ADMIN_USERNAME = (
    "Отправьте @username будущего администратора (например, <code>@ivan_petrov</code>).\n\n"
    "Если человек уже запускал бота, права будут выданы сразу. Если нет — "
    "права вступят в силу, когда он впервые откроет бота."
)


def admin_added(a: AdminView) -> str:
    if a.pending:
        return (
            f"@{q(a.username)} добавлен в администраторы. Пользователь ещё не запускал бота — "
            "права вступят в силу при первом запуске."
        )
    return f"{_admin_line(a)} назначен администратором. Уведомление отправлено."


def admin_removed(a: AdminView) -> str:
    return truncate(f"{_admin_label(a)}: права администратора сняты.", ALERT_LIMIT)


ADMIN_GRANTED = f"Вам выданы права администратора. Панель доступна по кнопке «{BTN_ADMIN}»."
ADMIN_REVOKED = "Права администратора сняты."


# ---------------------------------------------------------------- удаление матча

PICK_ROUND_TO_DELETE = "Выберите тур, из которого нужно удалить матч:"
NO_ROUNDS_TO_DELETE = "В текущем турнире нет туров."


def delete_pick_match(round_: Round) -> str:
    return f"<b>{q(round_.title)}</b>\nВыберите матч для удаления:"


def delete_confirm(preview: MatchDeletePreview) -> str:
    m = preview.match
    n = preview.predictions
    lines = [
        f"Удалить матч «<b>{match_title(m)}</b>» ({fmt_datetime(m.starts_at)})?",
        "",
        f"Прогнозов на матч: {n}" + (" — они будут удалены." if n else "."),
    ]
    if preview.has_result:
        lines.append("Результат матча уже внесён — начисленные за него баллы будут сняты.")
    if preview.is_last_in_round:
        lines.append(f"Это единственный матч тура — тур «{q(preview.round.title)}» будет удалён целиком.")
    lines.append("\nДействие необратимо.")
    return "\n".join(lines)


def match_deleted(result: MatchDeleteResult) -> str:
    m = result.match
    text = f"Матч {m.home_team} — {m.away_team} удалён."
    if result.round_deleted:
        text += f" Тур «{result.round.title}» удалён: в нём не осталось матчей."
    elif result.new_deadline:
        text += f" Приём прогнозов по туру теперь до {fmt_datetime(result.new_deadline)} (МСК)."
    return truncate(text, ALERT_LIMIT)
