import pytest
from sqlalchemy.orm import sessionmaker

from purdue_seat_watch.db import Subscription, get_engine, init_db
from purdue_seat_watch.emailer import EmailNotifier
from purdue_seat_watch.watcher import SeatWatcher
from purdue_seat_watch.worker import build_watcher


@pytest.fixture
def session_factory(tmp_path, monkeypatch):
    engine = get_engine(f"sqlite:///{tmp_path / 'test.db'}")
    init_db(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr("purdue_seat_watch.worker.SessionLocal", factory)
    monkeypatch.setenv("EMAIL_FROM", "test@example.com")
    monkeypatch.setenv("RESEND_API_KEY", "fake")
    return factory


def test_build_watcher_coalesces_one_watch_per_unique_course(session_factory):
    with session_factory() as session:
        session.add(Subscription(email="a@purdue.edu", term="202710", subject="CS", course_number="35200", section="LE1"))
        session.add(Subscription(email="b@purdue.edu", term="202710", subject="CS", course_number="35200", section="P02"))
        session.add(Subscription(email="c@purdue.edu", term="202710", subject="CS", course_number="18000", section="L01"))
        session.commit()

    watcher = build_watcher(interval_seconds=90)

    assert isinstance(watcher, SeatWatcher)
    assert isinstance(watcher._notifier, EmailNotifier)
    courses = {(w.term, w.subject, w.course_number) for w in watcher.watches}
    assert courses == {("202710", "CS", "35200"), ("202710", "CS", "18000")}


def test_build_watcher_narrows_to_requested_sections(session_factory):
    with session_factory() as session:
        session.add(Subscription(email="a@purdue.edu", term="202710", subject="CS", course_number="35200", section="LE1"))
        session.add(Subscription(email="b@purdue.edu", term="202710", subject="CS", course_number="35200", section="P02"))
        session.commit()

    watcher = build_watcher(interval_seconds=90)

    (watch,) = watcher.watches
    assert watch.sections == frozenset({"LE1", "P02"})
    assert watch.section is None  # narrowing goes through the plural `sections` field, not `section`


def test_build_watcher_falls_back_to_all_sections_for_legacy_any_section_row(session_factory):
    with session_factory() as session:
        session.add(Subscription(email="a@purdue.edu", term="202710", subject="CS", course_number="35200", section=""))
        session.add(Subscription(email="b@purdue.edu", term="202710", subject="CS", course_number="35200", section="LE1"))
        session.commit()

    watcher = build_watcher(interval_seconds=90)

    (watch,) = watcher.watches
    assert watch.sections is None  # "" present -> check every section, same as pre-required-section behavior
    assert watch.section is None


def test_build_watcher_with_no_subscriptions_yields_no_watches(session_factory):
    watcher = build_watcher(interval_seconds=90)
    assert watcher.watches == ()
