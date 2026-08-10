from __future__ import annotations

import logging
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from purdue_seat_watch import banner
from purdue_seat_watch.db import SessionLocal, Subscription, count_distinct_emails, count_subscriptions_for_email, init_db
from purdue_seat_watch.term import term_code

logger = logging.getLogger(__name__)

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


@app.get("/api/sections")
def api_sections(year: int, season: str, subject: str, course_number: str):
    """Live section + meeting-time lookup for the signup form's autocomplete.
    Best-effort: any failure (bad term, Banner hiccup) just yields no results
    rather than an error, so the form still works if this widget can't."""
    subject = subject.strip().upper()
    course_number = course_number.strip()
    try:
        term = term_code(year, season)
    except ValueError:
        return {"sections": []}
    if not subject or not course_number:
        return {"sections": []}

    try:
        sections = banner.search_sections(term, subject, course_number)
    except Exception:
        return {"sections": []}

    return {
        "sections": [
            {
                "section_code": s.section_code,
                "meetings": [{"days": m.days, "time": m.time, "type": m.type} for m in s.meetings],
            }
            for s in sections
        ]
    }


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
        try:
            real_sections = banner.search_sections(term, subject, course_number)
        except Exception:
            # Banner hiccup: don't block a legitimate signup over an infra blip --
            # the worker will just find nothing to watch if the section was bad anyway.
            logger.warning("Could not verify %s %s-%s against Banner; allowing signup unverified", subject, course_number, section, exc_info=True)
        else:
            if section not in {s.section_code for s in real_sections}:
                errors.append(f"'{section}' isn't a real section for {subject} {course_number} this term -- pick one from the list.")

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
