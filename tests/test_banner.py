from pathlib import Path

import pytest
import requests
import responses

from purdue_seat_watch import banner
from purdue_seat_watch.models import SeatInfo

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


@responses.activate
def test_search_sections_parses_real_fixture():
    responses.add(responses.POST, banner.SEARCH_URL, body=_fixture("search_results_cs18000.html"), status=200)

    sections = banner.search_sections("202710", "CS", "18000")

    assert len(sections) == 41
    first = sections[0]
    assert first.crn == "13610"
    assert first.subject == "CS"
    assert first.course_number == "18000"
    assert first.section_code == "001"
    assert first.title == "Problem Solving And Object-Oriented Programming"


@responses.activate
def test_search_sections_returns_empty_list_when_none_found():
    responses.add(responses.POST, banner.SEARCH_URL, body=_fixture("search_results_empty.html"), status=200)

    assert banner.search_sections("202710", "CS", "99999") == []


@responses.activate
def test_get_seat_info_parses_open_seats():
    responses.add(responses.GET, banner.DETAIL_URL, body=_fixture("detail_seats_open.html"), status=200)

    seats = banner.get_seat_info("202710", "13216")

    assert seats == SeatInfo(
        capacity=50, actual=40, remaining=10, waitlist_capacity=0, waitlist_actual=0, waitlist_remaining=0
    )
    assert seats.is_open


@responses.activate
def test_get_seat_info_parses_full_course():
    responses.add(responses.GET, banner.DETAIL_URL, body=_fixture("detail_seats_full.html"), status=200)

    seats = banner.get_seat_info("202710", "13216")

    assert seats.remaining == 0
    assert not seats.is_open


@responses.activate
def test_get_seat_info_raises_on_server_error():
    responses.add(responses.GET, banner.DETAIL_URL, body=_fixture("detail_server_error.html"), status=500)

    with pytest.raises(requests.HTTPError):
        banner.get_seat_info("202710", "13216")


def test_parse_seat_info_raises_banner_parse_error_on_unexpected_html():
    with pytest.raises(banner.BannerParseError):
        banner.parse_seat_info("<html><body>not a Banner page</body></html>")
