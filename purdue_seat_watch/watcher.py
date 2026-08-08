from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Protocol

from purdue_seat_watch.models import Section, SeatInfo
from purdue_seat_watch.notify import Notifier

logger = logging.getLogger(__name__)


class BannerClient(Protocol):
    def search_sections(self, term: str, subject: str, course_number: str) -> list[Section]: ...
    def get_seat_info(self, term: str, crn: str) -> SeatInfo: ...


@dataclass(frozen=True)
class Watch:
    term: str
    subject: str
    course_number: str
    section: str | None = None  # e.g. "001"; None means every section found
    crns: tuple[str, ...] | None = None  # bypass section search if you already know the CRN(s)


@dataclass(frozen=True)
class WatcherConfig:
    watches: tuple[Watch, ...]
    interval_seconds: int = 60


class SeatWatcher:
    def __init__(self, config: WatcherConfig, notifier: Notifier, banner: BannerClient):
        self._config = config
        self._notifier = notifier
        self._banner = banner
        self._last_remaining: dict[str, int] = {}

    def resolve_sections(self, watch: Watch) -> list[Section]:
        if watch.crns:
            return [
                Section(crn=crn, subject=watch.subject, course_number=watch.course_number, section_code="?", title="")
                for crn in watch.crns
            ]
        sections = self._banner.search_sections(watch.term, watch.subject, watch.course_number)
        if watch.section:
            sections = [s for s in sections if s.section_code == watch.section]
        return sections

    def check_once(self) -> None:
        for watch in self._config.watches:
            try:
                sections = self.resolve_sections(watch)
            except Exception:
                logger.exception("Failed to resolve sections for %s %s", watch.subject, watch.course_number)
                continue

            if not sections:
                logger.warning("No sections found for %s %s (term %s)", watch.subject, watch.course_number, watch.term)

            for section in sections:
                self._check_section(watch.term, section)

    def _check_section(self, term: str, section: Section) -> None:
        try:
            seats = self._banner.get_seat_info(term, section.crn)
        except Exception:
            logger.exception("Failed to fetch seat info for CRN %s", section.crn)
            return

        was_open = self._last_remaining.get(section.crn, 0) > 0
        self._last_remaining[section.crn] = seats.remaining

        label = f"{section.subject} {section.course_number}-{section.section_code}".strip()
        logger.info("%s (CRN %s): %d/%d remaining", label, section.crn, seats.remaining, seats.capacity)

        if seats.is_open and not was_open:
            self._notifier.notify(
                title=f"Seat open: {label}",
                message=f"{seats.remaining} seat(s) now available (CRN {section.crn}).",
            )

    def run_forever(self) -> None:
        while True:
            self.check_once()
            time.sleep(self._config.interval_seconds)
