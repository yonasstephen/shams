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
