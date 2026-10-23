"""Centralized NBA season string utility."""

from datetime import date


def get_current_season() -> str:
    """Return the active NBA season string (e.g. '2025-26').

    Oct-Dec  -> first year of the new season  (e.g. Oct 2025 -> 2025-26)
    Jan-Sep  -> second year of the current season (e.g. Feb 2026 -> 2025-26)
    """
    today = date.today()
    year = today.year if today.month >= 10 else today.year - 1
    return f"{year}-{str(year + 1)[-2:]}"


def get_season_first_day(season: str) -> date:
    """Return the earliest day a season's games can fall on: October 1 of its first year.

    Opening night moves from year to year (2021-22 tipped off October 19, 2026-27 on
    October 20), so walking the schedule from a guessed opener can skip real games for
    good. Walking from October 1 cannot, and costs nothing: the box score fetcher reads
    the schedule's own date-to-games map, so empty days and preseason games are skipped
    without a request.

    Raises:
        ValueError: if ``season`` is not a season string such as ``2026-27``.
    """
    return date(int(season.split("-")[0]), 10, 1)
