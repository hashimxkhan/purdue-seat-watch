from __future__ import annotations

import logging
import os

import resend
from sqlalchemy import or_, select

from purdue_seat_watch.db import SessionLocal, Subscription
from purdue_seat_watch.notify import NotifyEvent

logger = logging.getLogger(__name__)


class EmailNotifier:
    """Notifier that looks up every subscriber watching the section that just
    opened (via the structured NotifyEvent) and emails each one individually."""

    def __init__(self, session_factory=SessionLocal, *, from_address: str | None = None, api_key: str | None = None):
        self._session_factory = session_factory
        self._from_address = from_address or os.environ["EMAIL_FROM"]
        resend.api_key = api_key or os.environ["RESEND_API_KEY"]

    def notify(self, title: str, message: str, *, event: NotifyEvent | None = None) -> None:
        if event is None:
            logger.warning("EmailNotifier.notify called without a NotifyEvent; nothing to look up. Skipping.")
            return
        recipients = self._matching_subscriber_emails(event)
        sent = 0
        for email in recipients:
            try:
                resend.Emails.send({
                    "from": self._from_address,
                    "to": [email],
                    "subject": title,
                    "text": message,
                })
                sent += 1
            except Exception:
                logger.exception("Failed to email %s for %s %s-%s", email, event.subject, event.course_number, event.section_code)
        logger.info("Emailed %d/%d subscriber(s) for %s %s-%s", sent, len(recipients), event.subject, event.course_number, event.section_code)

    def _matching_subscriber_emails(self, event: NotifyEvent) -> list[str]:
        with self._session_factory() as session:
            stmt = select(Subscription.email).where(
                Subscription.term == event.term,
                Subscription.subject == event.subject,
                Subscription.course_number == event.course_number,
                or_(Subscription.section == "", Subscription.section == event.section_code),
            )
            return [row[0] for row in session.execute(stmt).all()]
