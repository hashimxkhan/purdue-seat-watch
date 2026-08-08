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
        session.add(Subscription(email="a@purdue.edu", term="202710", subject="CS", course_number="35200", section=""))
        session.add(Subscription(email="b@purdue.edu", term="202710", subject="CS", course_number="35200", section="LE1"))
        session.add(Subscription(email="c@purdue.edu", term="202710", subject="CS", course_number="18000", section=""))
        session.commit()

    watcher = build_watcher(interval_seconds=90)

    assert isinstance(watcher, SeatWatcher)
    assert isinstance(watcher._notifier, EmailNotifier)
    courses = {(w.term, w.subject, w.course_number) for w in watcher.watches}
    assert courses == {("202710", "CS", "35200"), ("202710", "CS", "18000")}
    # coalesced watches carry no section filter -- SeatWatcher.resolve_sections fetches every
    # section of the course in one Banner search, letting EmailNotifier's own DB lookup do the
    # per-subscriber section matching instead
    assert all(w.section is None for w in watcher.watches)


def test_build_watcher_with_no_subscriptions_yields_no_watches(session_factory):
    watcher = build_watcher(interval_seconds=90)
    assert watcher.watches == ()
