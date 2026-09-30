"""Часовой пояс для общения с людьми. В БД и в сервисах всё время — UTC."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

DISPLAY_TZ = timezone(timedelta(hours=3), "МСК")


def to_display(dt: datetime) -> datetime:
    return dt.astimezone(DISPLAY_TZ)


def fmt_datetime(dt: datetime) -> str:
    """«01.10 19:00» по МСК."""
    return to_display(dt).strftime("%d.%m %H:%M")


def fmt_date(dt: datetime) -> str:
    """«01.10.2026» по МСК."""
    return to_display(dt).strftime("%d.%m.%Y")
