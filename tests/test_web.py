import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from purdue_seat_watch import web
from purdue_seat_watch.db import Subscription, get_engine, init_db


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
        "section": "",
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


def test_invalid_season_is_rejected(env):
    client, factory = env
    response = _submit(client, season="winter")

    assert response.status_code == 400
    assert _rows(factory) == []


def test_fourth_course_for_same_email_is_rejected(env):
    client, factory = env
    for course_number in ("35200", "18000", "24000"):
        assert _submit(client, course_number=course_number).status_code == 200

    response = _submit(client, course_number="25100")

    assert response.status_code == 400
    assert len(_rows(factory)) == 3


def test_subscriber_cap_blocks_new_emails_once_full(env):
    client, factory = env
    with factory() as session:
        session.add_all(
            Subscription(email=f"user{i}@purdue.edu", term="202710", subject="CS", course_number="35200", section="")
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
            Subscription(email=f"user{i}@purdue.edu", term="202710", subject="CS", course_number="35200", section="")
            for i in range(200)
        )
        session.commit()

    response = _submit(client, email="user0@purdue.edu", course_number="18000")

    assert response.status_code == 200
    assert len(_rows(factory)) == 201
