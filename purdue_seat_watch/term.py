"""Purdue Banner term code helpers.

Confirmed empirically against the live Class Schedule Search term dropdown
(2026-08-07): Fall terms are coded under the *following* calendar year, while
Spring and Summer use the current calendar year. E.g. Fall 2026 -> 202710,
Spring 2026 -> 202620, Summer 2026 -> 202630.

Winter term codes were not verified and are intentionally unsupported here
rather than guessed.
"""

_SEASON_SUFFIXES = {
    "spring": "20",
    "summer": "30",
    "fall": "10",
}


def term_code(year: int, season: str) -> str:
    """Build a Banner term code, e.g. term_code(2026, "fall") -> "202710"."""
    key = season.strip().lower()
    if key not in _SEASON_SUFFIXES:
        supported = ", ".join(sorted(_SEASON_SUFFIXES))
        raise ValueError(f"Unsupported season {season!r}; expected one of: {supported}")
    banner_year = year + 1 if key == "fall" else year
    return f"{banner_year}{_SEASON_SUFFIXES[key]}"
