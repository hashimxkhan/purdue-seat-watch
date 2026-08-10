import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from purdue_seat_watch import web
from purdue_seat_watch.db import Subscription, get_engine, init_db
from purdue_seat_watch.purdueio import SectionMeeting


def _fake_section(crn: str) -> SectionMeeting:
    return SectionMeeting(crn=crn, type="Lecture", schedule="Tuesday, Thursday, 10:30 AM - 11:45 AM", instructor="Jane Doe")


@pytest.fixture
def env(tmp_path, monkeypatch):
    engine = get_engine(f"sqlite:///{tmp_path / 'test.db'}")
    init_db(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override_get_session():
        with factory() as session:
            yield session

    # Schema is already created against the test engine above; stub out the
    # startup hook so it doesn't touch the real default (./local.db) engine.
    monkeypatch.setattr(web, "init_db", lambda: None)
    # /subscribe now verifies the submitted CRN against a live Purdue.io search --
    # default to a permissive fake so tests unrelated to that check aren't hitting
    # the network. Tests that care about this specifically override it themselves.
    monkeypatch.setattr(web.purdueio, "search_sections", lambda term, subject, course_number: [_fake_section("15451")])
    web.app.dependency_overrides[web.get_session] = override_get_session
    try:
        with TestClient(web.app) as test_client:
            yield test_client, factory
    finally:
        web.app.dependency_overrides.clear()


def _submit(client, **overrides):
    data = {
        "email": "student@purdue.edu",
        "year": 2026,
        "season": "fall",
        "subject": "CS",
        "course_number": "35200",
        "crn": "15451",
    }
    data.update(overrides)
    return client.post("/subscribe", data=data)


def _rows(factory):
    with factory() as session:
        return session.execute(select(Subscription)).scalars().all()


def test_valid_purdue_signup_creates_a_row(env):
    client, factory = env
    response = _submit(client)

    assert response.status_code == 200
    rows = _rows(factory)
    assert len(rows) == 1
    assert rows[0].email == "student@purdue.edu"
    assert rows[0].term == "202710"
    assert rows[0].crn == "15451"


def test_non_purdue_email_is_rejected(env):
    client, factory = env
    response = _submit(client, email="student@gmail.com")

    assert response.status_code == 400
    assert _rows(factory) == []


def test_duplicate_signup_does_not_create_a_second_row(env):
    client, factory = env
    _submit(client)
    response = _submit(client)

    assert response.status_code == 200
    assert "already" in response.text.lower()
    assert len(_rows(factory)) == 1


def test_empty_crn_is_rejected(env):
    client, factory = env
    response = _submit(client, crn="")

    assert response.status_code == 400
    assert _rows(factory) == []


def test_invalid_season_is_rejected(env):
    client, factory = env
    response = _submit(client, season="winter")

    assert response.status_code == 400
    assert _rows(factory) == []


def test_fourth_course_for_same_email_is_rejected(env, monkeypatch):
    client, factory = env
    # A CRN only ever belongs to one real course, so each "different course" needs a
    # distinct CRN -- reusing one across course numbers wouldn't reflect real data.
    monkeypatch.setattr(
        web.purdueio, "search_sections",
        lambda term, subject, course_number: [_fake_section(f"crn-{course_number}")],
    )
    for course_number in ("35200", "18000", "24000"):
        assert _submit(client, course_number=course_number, crn=f"crn-{course_number}").status_code == 200

    response = _submit(client, course_number="25100", crn="crn-25100")

    assert response.status_code == 400
    assert len(_rows(factory)) == 3


def test_subscriber_cap_blocks_new_emails_once_full(env):
    client, factory = env
    with factory() as session:
        session.add_all(
            Subscription(email=f"user{i}@purdue.edu", term="202710", subject="CS", course_number="35200", crn=str(i))
            for i in range(200)
        )
        session.commit()

    response = _submit(client, email="latecomer@purdue.edu")

    assert response.status_code == 400
    assert len(_rows(factory)) == 200


def test_subscriber_cap_does_not_block_an_existing_subscriber_adding_a_course(env):
    client, factory = env
    with factory() as session:
        session.add_all(
            Subscription(email=f"user{i}@purdue.edu", term="202710", subject="CS", course_number="35200", crn=str(i))
            for i in range(200)
        )
        session.commit()

    response = _submit(client, email="user0@purdue.edu", course_number="18000")

    assert response.status_code == 200
    assert len(_rows(factory)) == 201


def test_crn_not_offered_by_purdueio_is_rejected(env, monkeypatch):
    client, factory = env
    monkeypatch.setattr(web.purdueio, "search_sections", lambda term, subject, course_number: [_fake_section("15451")])

    response = _submit(client, crn="99999")  # not among the real CRNs for this course

    assert response.status_code == 400
    assert _rows(factory) == []


def test_crn_matching_a_real_section_is_accepted(env, monkeypatch):
    client, factory = env
    monkeypatch.setattr(
        web.purdueio, "search_sections",
        lambda term, subject, course_number: [_fake_section("15451"), _fake_section("15456")],
    )

    response = _submit(client, crn="15456")

    assert response.status_code == 200
    assert len(_rows(factory)) == 1


def test_signup_still_succeeds_when_purdueio_verification_fails(env, monkeypatch):
    client, factory = env

    def failing_search_sections(term, subject, course_number):
        raise RuntimeError("Purdue.io is down")

    monkeypatch.setattr(web.purdueio, "search_sections", failing_search_sections)

    response = _submit(client)  # can't verify the CRN, but shouldn't block the signup over an infra blip

    assert response.status_code == 200
    assert len(_rows(factory)) == 1


def test_api_sections_returns_sections_with_schedule_and_instructor(env, monkeypatch):
    client, _ = env

    def fake_search_sections(term, subject, course_number):
        assert (term, subject, course_number) == ("202710", "CS", "35200")
        return [SectionMeeting(crn="15451", type="Lecture", schedule="Tuesday, Thursday, 10:30 AM - 11:45 AM", instructor="Changhee Jung")]

    monkeypatch.setattr(web.purdueio, "search_sections", fake_search_sections)

    response = client.get("/api/sections", params={"year": 2026, "season": "fall", "subject": "CS", "course_number": "35200"})

    assert response.status_code == 200
    assert response.json() == {
        "sections": [
            {"crn": "15451", "type": "Lecture", "schedule": "Tuesday, Thursday, 10:30 AM - 11:45 AM", "instructor": "Changhee Jung"},
        ]
    }


def test_api_sections_omits_instructor_when_not_available(env, monkeypatch):
    client, _ = env
    monkeypatch.setattr(
        web.purdueio, "search_sections",
        lambda term, subject, course_number: [SectionMeeting(crn="11909", type="Lab", schedule="Wednesday, 2:30 PM - 3:20 PM", instructor=None)],
    )

    response = client.get("/api/sections", params={"year": 2026, "season": "fall", "subject": "CS", "course_number": "35200"})

    assert response.json()["sections"][0]["instructor"] is None


def test_api_sections_returns_empty_list_for_invalid_season(env):
    client, _ = env

    response = client.get("/api/sections", params={"year": 2026, "season": "winter", "subject": "CS", "course_number": "35200"})

    assert response.status_code == 200
    assert response.json() == {"sections": []}


def test_api_sections_returns_empty_list_when_purdueio_fails(env, monkeypatch):
    client, _ = env

    def failing_search_sections(term, subject, course_number):
        raise RuntimeError("Purdue.io is down")

    monkeypatch.setattr(web.purdueio, "search_sections", failing_search_sections)

    response = client.get("/api/sections", params={"year": 2026, "season": "fall", "subject": "CS", "course_number": "35200"})

    assert response.status_code == 200
    assert response.json() == {"sections": []}
