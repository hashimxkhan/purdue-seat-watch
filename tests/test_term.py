import pytest

from purdue_seat_watch.term import term_code


@pytest.mark.parametrize(
    "year, season, expected",
    [
        (2026, "fall", "202710"),
        (2026, "Fall", "202710"),
        (2026, "spring", "202620"),
        (2026, "summer", "202630"),
    ],
)
def test_term_code_matches_confirmed_live_values(year, season, expected):
    assert term_code(year, season) == expected


def test_term_code_rejects_unsupported_season():
    with pytest.raises(ValueError, match="Unsupported season"):
        term_code(2026, "winter")
