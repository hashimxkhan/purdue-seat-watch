"""Client for Purdue's public (unauthenticated) Banner self-service endpoints.

Both endpoints used here require no login:

- bwckschd.p_get_crse_unsec: searches class sections for a term/subject/course number.
- bwckschd.p_disp_detail_sched: returns live seat counts for a single CRN.

The exact POST body for the search endpoint was captured from a real browser
form submission -- this legacy Oracle mod_plsql CGI throws a bare 500 if
extra/unexpected parameters (e.g. a stray submit-button field) are included,
so the parameter list below is intentionally exact rather than "obviously
equivalent."
"""

from __future__ import annotations

import re

import requests
from bs4 import BeautifulSoup

from purdue_seat_watch.models import Section, SeatInfo

BASE_URL = "https://selfservice.mypurdue.purdue.edu/prod"
SEARCH_URL = f"{BASE_URL}/bwckschd.p_get_crse_unsec"
DETAIL_URL = f"{BASE_URL}/bwckschd.p_disp_detail_sched"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}

_SECTION_LINE = re.compile(
    r"^(?P<title>.+) - (?P<crn>\d+) - (?P<subject>[A-Z]+) (?P<course_number>\S+) - (?P<section>\S+)$"
)
_CRN_IN_HREF = re.compile(r"crn_in=(\d+)")


class BannerError(Exception):
    """Base class for errors talking to or parsing Banner responses."""


class BannerParseError(BannerError):
    """Raised when a Banner response doesn't look the way we expect."""


def _search_payload(term: str, subject: str, course_number: str) -> list[tuple[str, str]]:
    # Order and duplicate keys mirror the real browser submission exactly.
    return [
        ("term_in", term),
        ("sel_subj", "dummy"),
        ("sel_day", "dummy"),
        ("sel_schd", "dummy"),
        ("sel_insm", "dummy"),
        ("sel_camp", "dummy"),
        ("sel_levl", "dummy"),
        ("sel_sess", "dummy"),
        ("sel_instr", "dummy"),
        ("sel_ptrm", "dummy"),
        ("sel_attr", "dummy"),
        ("sel_subj", subject.upper()),
        ("sel_crse", str(course_number)),
        ("sel_title", ""),
        ("sel_schd", "%"),
        ("sel_insm", "%"),
        ("sel_from_cred", ""),
        ("sel_to_cred", ""),
        ("sel_camp", "%"),
        ("sel_ptrm", "%"),
        ("sel_instr", "%"),
        ("sel_sess", "%"),
        ("sel_attr", "%"),
        ("begin_hh", "0"),
        ("begin_mi", "0"),
        ("begin_ap", "a"),
        ("end_hh", "0"),
        ("end_mi", "0"),
        ("end_ap", "a"),
    ]


def search_sections(
    term: str, subject: str, course_number: str, *, session: requests.Session | None = None, timeout: int = 20
) -> list[Section]:
    """Look up every section Banner has for a subject + course number in a term."""
    http = session or requests
    response = http.post(
        SEARCH_URL,
        data=_search_payload(term, subject, course_number),
        headers=_HEADERS,
        timeout=timeout,
    )
    response.raise_for_status()
    return parse_search_results(response.text)


def get_seat_info(
    term: str, crn: str, *, session: requests.Session | None = None, timeout: int = 20
) -> SeatInfo:
    """Fetch live capacity/actual/remaining seat counts for a single CRN."""
    http = session or requests
    response = http.get(
        DETAIL_URL,
        params={"term_in": term, "crn_in": crn},
        headers=_HEADERS,
        timeout=timeout,
    )
    response.raise_for_status()
    return parse_seat_info(response.text)


def parse_search_results(html: str) -> list[Section]:
    soup = BeautifulSoup(html, "html.parser")
    if "No classes were found" in soup.get_text():
        return []

    sections: list[Section] = []
    for header_cell in soup.select("th.ddlabel"):
        link = header_cell.find("a")
        if link is None:
            continue
        match = _SECTION_LINE.match(link.get_text(strip=True))
        if not match:
            continue
        href_match = _CRN_IN_HREF.search(link.get("href", ""))
        crn = href_match.group(1) if href_match else match.group("crn")
        sections.append(
            Section(
                crn=crn,
                subject=match.group("subject"),
                course_number=match.group("course_number"),
                section_code=match.group("section"),
                title=match.group("title").strip(),
            )
        )
    return sections


def parse_seat_info(html: str) -> SeatInfo:
    soup = BeautifulSoup(html, "html.parser")
    caption = soup.find("caption", string=re.compile("Registration Availability"))
    if caption is None:
        raise BannerParseError(
            "Could not find a 'Registration Availability' table in the response "
            "(the CRN/term may be invalid, or Banner returned an error page)."
        )

    table = caption.find_parent("table")
    seat_cells: list[str] | None = None
    waitlist_cells: list[str] | None = None
    for row in table.find_all("tr"):
        header = row.find("th")
        if header is None:
            continue
        label = header.get_text(strip=True)
        cells = [cell.get_text(strip=True) for cell in row.find_all("td")]
        if label == "Seats":
            seat_cells = cells
        elif label == "Waitlist Seats":
            waitlist_cells = cells

    if seat_cells is None or waitlist_cells is None:
        raise BannerParseError("Registration Availability table was missing the Seats/Waitlist rows.")

    try:
        capacity, actual, remaining = (int(v) for v in seat_cells)
        wl_capacity, wl_actual, wl_remaining = (int(v) for v in waitlist_cells)
    except ValueError as exc:
        raise BannerParseError(f"Non-numeric seat counts in response: {exc}") from exc

    return SeatInfo(
        capacity=capacity,
        actual=actual,
        remaining=remaining,
        waitlist_capacity=wl_capacity,
        waitlist_actual=wl_actual,
        waitlist_remaining=wl_remaining,
    )
