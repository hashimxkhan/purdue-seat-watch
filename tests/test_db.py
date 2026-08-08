import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from purdue_seat_watch.db import (
    DbSeatStateStore,
    Subscription,
    count_distinct_emails,
    count_subscriptions_for_email,
    get_engine,
    get_unique_courses,
    init_db,
)


@pytest.fixture
def session_factory(tmp_path):
    engine = get_engine(f"sqlite:///{tmp_path / 'test.db'}")
    init_db(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _sub(email, term="202710", subject="CS", course_number="35200", section=""):
    return Subscription(email=email, term=term, subject=subject, course_number=course_number, section=section)


def test_duplicate_subscription_is_rejected(session_factory):
    with session_factory() as session:
        session.add(_sub("a@purdue.edu"))
        session.commit()

    with session_factory() as session:
        session.add(_sub("a@purdue.edu"))
        with pytest.raises(IntegrityError):
            session.commit()


def test_different_section_is_not_a_duplicate(session_factory):
    with session_factory() as session:
        session.add(_sub("a@purdue.edu", section=""))
        session.add(_sub("a@purdue.edu", section="LE1"))
        session.commit()  # should not raise

    with session_factory() as session:
        assert session.query(Subscription).count() == 2


def test_get_unique_courses_dedupes_across_subscribers(session_factory):
    with session_factory() as session:
        session.add(_sub("a@purdue.edu", course_number="35200"))
        session.add(_sub("b@purdue.edu", course_number="35200", section="LE1"))
        session.add(_sub("c@purdue.edu", course_number="18000"))
        session.commit()

    courses = get_unique_courses(session_factory)
    assert sorted(courses) == [("202710", "CS", "18000"), ("202710", "CS", "35200")]


def test_seat_state_store_persists_across_instances(session_factory):
    store1 = DbSeatStateStore(session_factory)
    store1["12345"] = 4

    store2 = DbSeatStateStore(session_factory)  # simulates a worker restart
    assert store2["12345"] == 4


def test_seat_state_store_raises_key_error_for_unknown_crn(session_factory):
    store = DbSeatStateStore(session_factory)
    with pytest.raises(KeyError):
        store["nope"]


def test_count_distinct_emails(session_factory):
    with session_factory() as session:
        session.add(_sub("a@purdue.edu", course_number="35200"))
        session.add(_sub("a@purdue.edu", course_number="18000"))
        session.add(_sub("b@purdue.edu", course_number="35200"))
        session.commit()

        assert count_distinct_emails(session) == 2
        assert count_subscriptions_for_email(session, "a@purdue.edu") == 2
        assert count_subscriptions_for_email(session, "nobody@purdue.edu") == 0
