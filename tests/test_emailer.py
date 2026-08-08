import pytest
from sqlalchemy.orm import sessionmaker

from purdue_seat_watch.db import Subscription, get_engine, init_db
from purdue_seat_watch.emailer import EmailNotifier
from purdue_seat_watch.notify import NotifyEvent


@pytest.fixture
def session_factory(tmp_path):
    engine = get_engine(f"sqlite:///{tmp_path / 'test.db'}")
    init_db(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        session.add(Subscription(email="any@purdue.edu", term="202710", subject="CS", course_number="35200", section=""))
        session.add(Subscription(email="le1@purdue.edu", term="202710", subject="CS", course_number="35200", section="LE1"))
        session.add(Subscription(email="p01@purdue.edu", term="202710", subject="CS", course_number="35200", section="P01"))
        session.add(Subscription(email="other@purdue.edu", term="202710", subject="CS", course_number="18000", section=""))
        session.commit()
    return factory


@pytest.fixture
def sent_emails(monkeypatch):
    calls = []

    def fake_send(params):
        calls.append(params)

    monkeypatch.setattr("purdue_seat_watch.emailer.resend.Emails.send", fake_send)
    return calls


def _event(section_code="LE1"):
    return NotifyEvent(
        term="202710", subject="CS", course_number="35200", section_code=section_code,
        crn="15451", remaining=5, capacity=132,
    )


def test_emails_any_section_and_matching_section_subscribers(session_factory, sent_emails):
    notifier = EmailNotifier(session_factory, from_address="test@example.com", api_key="fake")

    notifier.notify("Seat open: CS 35200-LE1", "5 seat(s) now available.", event=_event("LE1"))

    recipients = {call["to"][0] for call in sent_emails}
    assert recipients == {"any@purdue.edu", "le1@purdue.edu"}


def test_does_not_email_other_section_or_other_course_subscribers(session_factory, sent_emails):
    notifier = EmailNotifier(session_factory, from_address="test@example.com", api_key="fake")

    notifier.notify("Seat open: CS 35200-LE1", "5 seat(s) now available.", event=_event("LE1"))

    recipients = {call["to"][0] for call in sent_emails}
    assert "p01@purdue.edu" not in recipients
    assert "other@purdue.edu" not in recipients


def test_sends_one_call_per_recipient_not_a_shared_to_list(session_factory, sent_emails):
    notifier = EmailNotifier(session_factory, from_address="test@example.com", api_key="fake")

    notifier.notify("Seat open: CS 35200-LE1", "5 seat(s) now available.", event=_event("LE1"))

    assert len(sent_emails) == 2
    for call in sent_emails:
        assert len(call["to"]) == 1


def test_no_op_without_an_event(session_factory, sent_emails):
    notifier = EmailNotifier(session_factory, from_address="test@example.com", api_key="fake")

    notifier.notify("Title", "Message", event=None)

    assert sent_emails == []


def test_a_failed_send_does_not_stop_the_remaining_recipients(session_factory, monkeypatch):
    sent = []

    def flaky_send(params):
        if params["to"][0] == "any@purdue.edu":
            raise RuntimeError("simulated Resend API failure")
        sent.append(params)

    monkeypatch.setattr("purdue_seat_watch.emailer.resend.Emails.send", flaky_send)
    notifier = EmailNotifier(session_factory, from_address="test@example.com", api_key="fake")

    notifier.notify("Seat open: CS 35200-LE1", "5 seat(s) now available.", event=_event("LE1"))  # does not raise

    assert {call["to"][0] for call in sent} == {"le1@purdue.edu"}


def test_no_matching_subscribers_sends_nothing(session_factory, sent_emails):
    notifier = EmailNotifier(session_factory, from_address="test@example.com", api_key="fake")

    event = NotifyEvent(
        term="202710", subject="CS", course_number="50200", section_code="001",
        crn="99999", remaining=1, capacity=30,
    )  # no subscribers exist for this course at all
    notifier.notify("Seat open", "1 seat", event=event)

    assert sent_emails == []
