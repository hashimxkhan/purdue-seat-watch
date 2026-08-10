"""Client for Purdue.io (api.purdue.io) -- a third-party, community-run OData
mirror of Purdue's course catalog: https://github.com/Purdue-io/PurdueApi.

Used only for course/section/meeting-time lookups (the signup form's live
suggestions, and section validation), so those don't have to hit Banner at
all. Purdue.io has no seat-availability data whatsoever -- that still comes
exclusively from banner.py's get_seat_info, which is unavoidable since no
other source has it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import requests

BASE_URL = "https://api.purdue.io/odata"

_DURATION_RE = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?")


class PurdueIoError(Exception):
    """Base class for errors talking to or parsing Purdue.io responses."""


@dataclass(frozen=True)
class SectionMeeting:
    crn: str
    type: str  # e.g. "Lecture", "Laboratory"
    schedule: str  # e.g. "Tuesday, Thursday, 10:30 AM - 11:45 AM"
    instructor: str | None


def search_sections(
    term: str, subject: str, course_number: str, *, session: requests.Session | None = None, timeout: int = 15
) -> list[SectionMeeting]:
    """Look up every section Purdue.io has for a subject + course number in a term."""
    http = session or requests
    filter_query = (
        f"Course/Subject/Abbreviation eq '{subject}' and "
        f"Course/Number eq '{course_number}' and "
        f"Term/Code eq '{term}'"
    )
    response = http.get(
        f"{BASE_URL}/Classes",
        params={"$filter": filter_query, "$expand": "Sections($expand=Meetings($expand=Instructors))"},
        timeout=timeout,
    )
    response.raise_for_status()
    return _parse_classes(response.json())


def _parse_classes(data: dict) -> list[SectionMeeting]:
    by_crn: dict[str, dict] = {}
    order: list[str] = []

    for cls in data.get("value", []):
        for section in cls.get("Sections", []):
            crn = section.get("Crn")
            if not crn:
                continue
            if crn not in by_crn:
                by_crn[crn] = {"type": section.get("Type") or "Class", "parts": [], "instructor": None}
                order.append(crn)

            meetings = section.get("Meetings") or []
            if not meetings:
                by_crn[crn]["parts"].append("TBA")
            for meeting in meetings:
                by_crn[crn]["parts"].append(_format_meeting(meeting))
                if by_crn[crn]["instructor"] is None:
                    instructors = meeting.get("Instructors") or []
                    if instructors:
                        by_crn[crn]["instructor"] = instructors[0].get("Name")

    return [
        SectionMeeting(
            crn=crn,
            type=by_crn[crn]["type"],
            schedule=" & ".join(dict.fromkeys(by_crn[crn]["parts"])) or "TBA",
            instructor=by_crn[crn]["instructor"],
        )
        for crn in order
    ]


def _format_meeting(meeting: dict) -> str:
    days = meeting.get("DaysOfWeek") or "TBA"
    time_range = _format_time_range(meeting.get("StartTime"), meeting.get("Duration"))
    return f"{days}, {time_range}" if time_range else days


def _format_time_range(start_time: str | None, duration: str | None) -> str | None:
    if not start_time:
        return None
    try:
        hh, mm = start_time.split(":", 2)[:2]
        start_minutes = int(hh) * 60 + int(mm)
    except ValueError:
        return None

    duration_minutes = 0
    if duration:
        match = _DURATION_RE.match(duration)
        if match:
            hours, minutes = match.groups()
            duration_minutes = (int(hours) if hours else 0) * 60 + (int(minutes) if minutes else 0)

    if not duration_minutes:
        return _format_clock(start_minutes)
    return f"{_format_clock(start_minutes)} - {_format_clock(start_minutes + duration_minutes)}"


def _format_clock(total_minutes: int) -> str:
    total_minutes %= 24 * 60
    hour24, minute = divmod(total_minutes, 60)
    period = "AM" if hour24 < 12 else "PM"
    hour12 = hour24 % 12 or 12
    return f"{hour12}:{minute:02d} {period}"
