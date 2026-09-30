"""ORM-модели SQLAlchemy. Работают и на SQLite, и на PostgreSQL.

Все даты — в UTC. В PostgreSQL это TIMESTAMPTZ, в SQLite — TEXT в формате
ISO-8601 ("2026-10-01T16:00:00Z"), который корректно сравнивается строками,
поэтому проверки вида `deadline_at > :now` работают на обеих базах.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Dialect,
    Enum,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    TypeDecorator,
    UniqueConstraint,
    false,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import TypeEngine

# Явные имена ограничений нужны Alembic: в SQLite изменение таблиц идёт через
# batch-режим (пересоздание таблицы), и безымянные constraint-ы он не найдёт.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

UTC_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def utcnow() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def make_nickname_key(nickname: str) -> str:
    """Ключ уникальности ника: без учёта регистра в любом алфавите, ё == е.

    COLLATE NOCASE в SQLite не подходит: он приводит к одному регистру только
    латиницу, и «Вася» с «вася» для него — разные ники.
    """
    return nickname.casefold().replace("ё", "е")


class UtcDateTime(TypeDecorator[datetime]):
    """datetime с часовым поясом, всегда в UTC.

    PostgreSQL: TIMESTAMPTZ. SQLite: TEXT 'YYYY-MM-DDTHH:MM:SSZ'.
    Наивные datetime отклоняются: так ошибка с часовым поясом всплывёт сразу,
    а не превратится в тихий сдвиг дедлайна на 3 часа.
    """

    impl = String(20)
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[object]:
        if dialect.name == "sqlite":
            return dialect.type_descriptor(String(20))
        return dialect.type_descriptor(DateTime(timezone=True))

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> str | datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("UtcDateTime принимает только datetime с tzinfo")
        value = value.astimezone(UTC)
        return value.strftime(UTC_FORMAT) if dialect.name == "sqlite" else value

    def process_result_value(self, value: str | datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, str):
            return datetime.strptime(value, UTC_FORMAT).replace(tzinfo=UTC)
        return value.astimezone(UTC)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


# ---------------------------------------------------------------- enums


class Outcome(StrEnum):
    HOME = "1"   # П1
    DRAW = "X"   # Х
    AWAY = "2"   # П2


class TournamentStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class MatchStatus(StrEnum):
    SCHEDULED = "scheduled"
    FINISHED = "finished"
    CANCELLED = "cancelled"


def _str_enum(enum_cls: type[StrEnum], name: str) -> Enum:
    """Enum, хранящийся как TEXT со значениями (а не именами) и CHECK-ограничением."""
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        values_callable=lambda cls: [member.value for member in cls],
        length=max(len(member.value) for member in enum_cls),
    )


# ---------------------------------------------------------------- tables


class User(Base):
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    nickname: Mapped[str] = mapped_column(String(32))                   # как показывать
    nickname_key: Mapped[str] = mapped_column(String(32), unique=True)  # make_nickname_key(nickname)
    tg_username: Mapped[str | None] = mapped_column(String(32))
    is_banned: Mapped[bool] = mapped_column(
        Boolean(create_constraint=True, name="is_banned"),
        default=False,
        server_default=false(),
    )
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime, default=utcnow
    )

    predictions: Mapped[list[Prediction]] = relationship(
        back_populates="user", lazy="raise", passive_deletes=True
    )

    def __repr__(self) -> str:
        return f"User(telegram_id={self.telegram_id}, nickname={self.nickname!r})"


class Tournament(Base):
    __tablename__ = "tournaments"
    __table_args__ = (
        # Активный турнир может быть только один.
        Index(
            "ux_tournaments_one_active",
            "status",
            unique=True,
            sqlite_where=text("status = 'active'"),
            postgresql_where=text("status = 'active'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(128))
    status: Mapped[TournamentStatus] = mapped_column(
        _str_enum(TournamentStatus, "tournament_status"),
        default=TournamentStatus.ACTIVE,
        server_default=TournamentStatus.ACTIVE.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime, default=utcnow
    )
    archived_at: Mapped[datetime | None] = mapped_column(UtcDateTime)

    rounds: Mapped[list[Round]] = relationship(
        back_populates="tournament", lazy="raise", passive_deletes=True, order_by="Round.deadline_at"
    )
    snapshots: Mapped[list[LeaderboardSnapshot]] = relationship(
        back_populates="tournament",
        lazy="raise",
        passive_deletes=True,
        order_by="LeaderboardSnapshot.place",
    )

    def __repr__(self) -> str:
        return f"Tournament(id={self.id}, title={self.title!r}, status={self.status})"


class Round(Base):
    __tablename__ = "rounds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tournament_id: Mapped[int] = mapped_column(
        ForeignKey("tournaments.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(128))
    # Старт первого матча тура. Проставляется сервисом при загрузке матчей.
    deadline_at: Mapped[datetime] = mapped_column(UtcDateTime)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime, default=utcnow
    )

    tournament: Mapped[Tournament] = relationship(back_populates="rounds", lazy="raise")
    matches: Mapped[list[Match]] = relationship(
        back_populates="round", lazy="raise", passive_deletes=True, order_by="Match.starts_at"
    )

    def is_open(self, now: datetime | None = None) -> bool:
        return (now or utcnow()) < self.deadline_at

    def __repr__(self) -> str:
        return f"Round(id={self.id}, title={self.title!r}, deadline_at={self.deadline_at})"


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    round_id: Mapped[int] = mapped_column(ForeignKey("rounds.id", ondelete="CASCADE"), index=True)
    home_team: Mapped[str] = mapped_column(String(64))
    away_team: Mapped[str] = mapped_column(String(64))
    starts_at: Mapped[datetime] = mapped_column(UtcDateTime)
    # NULL — результат ещё не внесён.
    result: Mapped[Outcome | None] = mapped_column(_str_enum(Outcome, "result"))
    status: Mapped[MatchStatus] = mapped_column(
        _str_enum(MatchStatus, "match_status"),
        default=MatchStatus.SCHEDULED,
        server_default=MatchStatus.SCHEDULED.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime, default=utcnow
    )

    round: Mapped[Round] = relationship(back_populates="matches", lazy="raise")
    predictions: Mapped[list[Prediction]] = relationship(
        back_populates="match", lazy="raise", passive_deletes=True
    )

    @property
    def title(self) -> str:
        return f"{self.home_team} — {self.away_team}"

    def __repr__(self) -> str:
        return f"Match(id={self.id}, {self.title!r}, result={self.result})"


class Prediction(Base):
    __tablename__ = "predictions"
    __table_args__ = (UniqueConstraint("user_id", "match_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.telegram_id", ondelete="CASCADE"))
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), index=True)
    outcome: Mapped[Outcome] = mapped_column(_str_enum(Outcome, "outcome"))
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime, default=utcnow
    )
    # onupdate срабатывает только для ORM-UPDATE; в UPSERT (on_conflict_do_update)
    # репозиторий обязан проставлять updated_at явно.
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime, default=utcnow, onupdate=utcnow
    )

    user: Mapped[User] = relationship(back_populates="predictions", lazy="raise")
    match: Mapped[Match] = relationship(back_populates="predictions", lazy="raise")

    def __repr__(self) -> str:
        return f"Prediction(user_id={self.user_id}, match_id={self.match_id}, outcome={self.outcome})"


class LeaderboardSnapshot(Base):
    """Замороженная таблица лидеров, которая сохраняется при архивации турнира."""

    __tablename__ = "leaderboard_snapshots"

    tournament_id: Mapped[int] = mapped_column(
        ForeignKey("tournaments.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.telegram_id"), primary_key=True)
    nickname: Mapped[str] = mapped_column(String(32))  # ник на момент архивации
    place: Mapped[int] = mapped_column(Integer)          # при равных очках место общее
    points: Mapped[int] = mapped_column(Integer)
    predictions_count: Mapped[int] = mapped_column(Integer)

    tournament: Mapped[Tournament] = relationship(back_populates="snapshots", lazy="raise")

    def __repr__(self) -> str:
        return f"LeaderboardSnapshot(tournament_id={self.tournament_id}, place={self.place}, nickname={self.nickname!r})"


class Admin(Base):
    """Администратор, назначенный через бот (любым админом).

    Админы из ADMIN_IDS/OWNER_IDS (.env) здесь не хранятся. Если человек ещё
    не запускал бота, известен только username (telegram_id = NULL); к ID
    запись привязывается при первом его обращении к боту.
    """

    __tablename__ = "admins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    username: Mapped[str | None] = mapped_column(String(32), unique=True)   # в нижнем регистре, без @
    added_by: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)

    def __repr__(self) -> str:
        return f"Admin(id={self.id}, telegram_id={self.telegram_id}, username={self.username!r})"
