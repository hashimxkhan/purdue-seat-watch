from pathlib import Path

import pytest
import requests
import responses

from purdue_seat_watch import banner
from purdue_seat_watch.models import Meeting, SeatInfo

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
    assert first.meetings == (
        Meeting(type="Class", time="11:30 am - 1:20 pm", days="T", schedule_type="Laboratory"),
    )


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


def _section_html(meeting_rows: str) -> str:
    return f"""
    <table class="datadisplaytable">
    <tr><th class="ddlabel"><a href="/prod/bwckschd.p_disp_detail_sched?term_in=202710&crn_in=12345">
    Some Course - 12345 - CS 50200 - 001</a></th></tr>
    <tr><td class="dddefault">
    <table class="datadisplaytable"><caption>Scheduled Meeting Times</caption>
    <tr><th>Type</th><th>Time</th><th>Days</th><th>Where</th><th>Date Range</th><th>Schedule Type</th><th>Instructors</th></tr>
    {meeting_rows}
    </table>
    </td></tr>
    </table>
    """


def test_parse_search_results_captures_multiple_meeting_rows_for_one_section():
    row1 = "<tr><td>Class</td><td>9:30 am - 10:20 am</td><td>M</td><td>X</td><td>X</td><td>Lecture</td><td>X</td></tr>"
    row2 = "<tr><td>Class</td><td>1:30 pm - 2:20 pm</td><td>W</td><td>X</td><td>X</td><td>Recitation</td><td>X</td></tr>"
    sections = banner.parse_search_results(_section_html(row1 + row2))

    assert len(sections) == 1
    assert sections[0].meetings == (
        Meeting(type="Class", time="9:30 am - 10:20 am", days="M", schedule_type="Lecture"),
        Meeting(type="Class", time="1:30 pm - 2:20 pm", days="W", schedule_type="Recitation"),
    )


def test_parse_search_results_defaults_to_no_meetings_when_table_is_missing():
    html = """
    <table class="datadisplaytable">
    <tr><th class="ddlabel"><a href="/prod/bwckschd.p_disp_detail_sched?term_in=202710&crn_in=12345">
    Some Course - 12345 - CS 50200 - 001</a></th></tr>
    </table>
    """
    sections = banner.parse_search_results(html)

    assert len(sections) == 1
    assert sections[0].meetings == ()


def test_parse_seat_info_raises_banner_parse_error_on_unexpected_html():
    with pytest.raises(banner.BannerParseError):
        banner.parse_seat_info("<html><body>not a Banner page</body></html>")
