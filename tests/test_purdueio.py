from purdue_seat_watch.purdueio import SectionMeeting, _format_clock, _format_time_range, _parse_classes

# Shape captured from a real api.purdue.io response for CS 35200, Fall 2026
# (Classes?$filter=...&$expand=Sections($expand=Meetings($expand=Instructors))).
_REAL_SHAPE_RESPONSE = {
    "value": [
        {
            "Id": "c9025166-e492-4546-92d0-8b8cea2dd793",
            "Sections": [
                {
                    "Crn": "15451",
                    "Type": "Lecture",
                    "Meetings": [
                        {
                            "DaysOfWeek": "Tuesday, Thursday",
                            "StartTime": "10:30:00.0000000",
                            "Duration": "PT1H15M",
                            "Instructors": [{"Id": "x", "Name": "Changhee Jung", "Email": "chjung@purdue.edu"}],
                        }
                    ],
                },
                {
                    "Crn": "11909",
                    "Type": "Practice Study Observation",
                    "Meetings": [
                        {
                            "DaysOfWeek": "Wednesday",
                            "StartTime": "14:30:00.0000000",
                            "Duration": "PT50M",
                            "Instructors": [],
                        }
                    ],
                },
            ],
        }
    ]
}


def test_parse_classes_matches_real_response_shape():
    sections = _parse_classes(_REAL_SHAPE_RESPONSE)

    assert sections == [
        SectionMeeting(crn="15451", type="Lecture", schedule="Tuesday, Thursday, 10:30 AM - 11:45 AM", instructor="Changhee Jung"),
        SectionMeeting(crn="11909", type="Practice Study Observation", schedule="Wednesday, 2:30 PM - 3:20 PM", instructor=None),
    ]


def test_parse_classes_combines_multiple_meetings_for_one_crn():
    data = {
        "value": [
            {
                "Sections": [
                    {
                        "Crn": "20000",
                        "Type": "Lecture",
                        "Meetings": [
                            {"DaysOfWeek": "Monday", "StartTime": "09:30:00.0000000", "Duration": "PT50M", "Instructors": []},
                            {"DaysOfWeek": "Wednesday", "StartTime": "13:30:00.0000000", "Duration": "PT50M", "Instructors": []},
                        ],
                    }
                ]
            }
        ]
    }

    (section,) = _parse_classes(data)

    assert section.schedule == "Monday, 9:30 AM - 10:20 AM & Wednesday, 1:30 PM - 2:20 PM"


def test_parse_classes_handles_a_section_with_no_meetings():
    data = {"value": [{"Sections": [{"Crn": "30000", "Type": "Individual Study", "Meetings": []}]}]}

    (section,) = _parse_classes(data)

    assert section == SectionMeeting(crn="30000", type="Individual Study", schedule="TBA", instructor=None)


def test_parse_classes_dedupes_a_crn_appearing_in_multiple_classes():
    # Purdue.io nests Sections under Class; a cross-listed course could plausibly
    # surface the same CRN twice. Only one entry should come out.
    data = {
        "value": [
            {"Sections": [{"Crn": "40000", "Type": "Lecture", "Meetings": []}]},
            {"Sections": [{"Crn": "40000", "Type": "Lecture", "Meetings": []}]},
        ]
    }

    sections = _parse_classes(data)

    assert len(sections) == 1


def test_format_time_range_computes_end_time_from_duration():
    assert _format_time_range("10:30:00.0000000", "PT1H15M") == "10:30 AM - 11:45 AM"


def test_format_time_range_handles_missing_start_time():
    assert _format_time_range(None, "PT50M") is None


def test_format_clock_wraps_past_midnight():
    assert _format_clock(23 * 60 + 45 + 30) == "12:15 AM"  # 23:45 + 30min duration wraps to next day
