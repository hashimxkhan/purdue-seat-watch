from __future__ import annotations

import os
from collections.abc import Iterator, MutableMapping
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, UniqueConstraint, create_engine, event, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class Subscription(Base):
    """One subscriber's watch target. `section == ""` means 'any section'; kept as an
    empty string rather than NULL so the unique constraint below actually dedupes
    two 'any section' signups from the same email (SQL treats NULL != NULL)."""

    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    term: Mapped[str] = mapped_column(String(6), nullable=False)
    subject: Mapped[str] = mapped_column(String(10), nullable=False)
    course_number: Mapped[str] = mapped_column(String(10), nullable=False)
    section: Mapped[str] = mapped_column(String(10), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        UniqueConstraint("email", "term", "subject", "course_number", "section", name="uq_subscription_target"),
    )


class SeatState(Base):
    """Persisted replacement for SeatWatcher's in-memory `_last_remaining` dict, so
    the worker doesn't forget state (and re-fire every already-open seat as newly
    opened) across restarts. Keyed by CRN alone, matching the original dict's
    semantics exactly (an inherited limitation, not new: a CRN reused across two
    concurrently-watched terms would conflate -- not fixed here, flagged as a
    possible future follow-up)."""

    __tablename__ = "seat_states"

    crn: Mapped[str] = mapped_column(String(10), primary_key=True)
    term: Mapped[str] = mapped_column(String(6), nullable=False, default="")
    subject: Mapped[str] = mapped_column(String(10), nullable=False, default="")
    course_number: Mapped[str] = mapped_column(String(10), nullable=False, default="")
    section_code: Mapped[str] = mapped_column(String(10), nullable=False, default="")
    last_remaining: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


def get_engine(database_url: str | None = None):
    url = database_url or os.environ.get("DATABASE_URL", "sqlite:///./local.db")
    if url.startswith("postgres://"):  # Render/Heroku-style scheme; SQLAlchemy 2.x wants postgresql://
        url = url.replace("postgres://", "postgresql://", 1)
    is_sqlite = url.startswith("sqlite")
    connect_args = {"check_same_thread": False} if is_sqlite else {}
    engine = create_engine(url, connect_args=connect_args)
    if is_sqlite:
        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()
    return engine


_engine = get_engine()
SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)


def init_db(engine=None) -> None:
    Base.metadata.create_all(engine or _engine)


def get_unique_courses(session_factory=SessionLocal) -> list[tuple[str, str, str]]:
    with session_factory() as session:
        stmt = select(Subscription.term, Subscription.subject, Subscription.course_number).distinct()
        return [tuple(row) for row in session.execute(stmt).all()]


def count_distinct_emails(session: Session) -> int:
    return session.execute(select(func.count(func.distinct(Subscription.email)))).scalar_one()


def count_subscriptions_for_email(session: Session, email: str) -> int:
    stmt = select(func.count()).select_from(Subscription).where(Subscription.email == email)
    return session.execute(stmt).scalar_one()


class DbSeatStateStore(MutableMapping[str, int]):
    """MutableMapping adapter over the seat_states table, so it's a drop-in
    replacement for SeatWatcher's default in-memory `_last_remaining` dict via the
    `last_remaining=` constructor kwarg."""

    def __init__(self, session_factory=SessionLocal):
        self._session_factory = session_factory

    def __getitem__(self, crn: str) -> int:
        with self._session_factory() as session:
            row = session.get(SeatState, crn)
            if row is None:
                raise KeyError(crn)
            return row.last_remaining

    def __setitem__(self, crn: str, remaining: int) -> None:
        with self._session_factory() as session:
            row = session.get(SeatState, crn)
            if row is None:
                session.add(SeatState(crn=crn, last_remaining=remaining))
            else:
                row.last_remaining = remaining
            session.commit()

    def __delitem__(self, crn: str) -> None:
        with self._session_factory() as session:
            row = session.get(SeatState, crn)
            if row is None:
                raise KeyError(crn)
            session.delete(row)
            session.commit()

    def __iter__(self) -> Iterator[str]:
        with self._session_factory() as session:
            return iter([row[0] for row in session.execute(select(SeatState.crn)).all()])

    def __len__(self) -> int:
        with self._session_factory() as session:
            return session.execute(select(func.count()).select_from(SeatState)).scalar_one()
