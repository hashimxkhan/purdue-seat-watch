from __future__ import annotations

import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from purdue_seat_watch.db import SessionLocal, Subscription, count_distinct_emails, count_subscriptions_for_email, init_db
from purdue_seat_watch.term import term_code

MAX_SUBSCRIBERS = 200
MAX_COURSES_PER_EMAIL = 3


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Purdue Seat Watch", lifespan=_lifespan)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

_PURDUE_EMAIL_RE = re.compile(r"^[^@\s]+@purdue\.edu$", re.IGNORECASE)


def get_session() -> Session:
    with SessionLocal() as session:
        yield session


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "signup.html", {})


@app.post("/subscribe", response_class=HTMLResponse)
def subscribe(
    request: Request,
    email: str = Form(...),
    year: int = Form(...),
    season: str = Form(...),
    subject: str = Form(...),
    course_number: str = Form(...),
    section: str = Form(""),
    session: Session = Depends(get_session),
):
    email = email.strip().lower()
    subject = subject.strip().upper()
    course_number = course_number.strip()
    section = section.strip().upper()

    errors: list[str] = []
    if not _PURDUE_EMAIL_RE.match(email):
        errors.append("Email must be a @purdue.edu address.")
    term: str | None = None
    try:
        term = term_code(year, season)
    except ValueError as exc:
        errors.append(str(exc))
    if not subject or not course_number:
        errors.append("Subject and course number are required.")
    if not section:
        errors.append("Section is required -- look up the section code on Purdue's class search first.")

    if not errors:
        existing_for_email = count_subscriptions_for_email(session, email)
        if existing_for_email >= MAX_COURSES_PER_EMAIL:
            errors.append(f"You've reached the {MAX_COURSES_PER_EMAIL}-course limit.")
        elif existing_for_email == 0 and count_distinct_emails(session) >= MAX_SUBSCRIBERS:
            errors.append("We've hit our subscriber cap for now.")

    if errors:
        return templates.TemplateResponse(request, "signup.html", {"errors": errors}, status_code=400)

    session.add(Subscription(email=email, term=term, subject=subject, course_number=course_number, section=section))
    try:
        session.commit()
        status = "subscribed"
    except IntegrityError:
        session.rollback()
        status = "already_subscribed"

    return templates.TemplateResponse(request, "signup.html", {"status": status})
