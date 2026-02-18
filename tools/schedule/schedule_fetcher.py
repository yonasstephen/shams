"""Helpers for fetching NBA team schedules via nba_api."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Sequence

from tools.utils import nba_api_config  # noqa: F401  # pylint: disable=unused-import


@dataclass
class PlayerSchedule:
    player_id: int
    game_dates: Sequence[str]


def get_season_start_date(season: str = "2025-26") -> date:
    """Get the start date of an NBA season.

    Args:
        season: Season string (e.g., "2025-26")

    Returns:
        Season start date (typically October 21 of the first year)
    """
    # Parse season year
    try:
        year = int(season.split("-")[0])
        # NBA regular season typically starts on October 21 of the first year
        # For "2025-26", that's October 21, 2025
        return date(year, 10, 21)
    except (ValueError, IndexError):
        # Fallback to current date
        return date.today()


def fetch_player_upcoming_games_from_cache(
    player_id: int, start_date: str, end_date: str, season: str
) -> PlayerSchedule:
    """Get player schedule from cache (no API calls).

    This function uses the pre-cached team schedules and player-to-team index
    to determine a player's upcoming games without making any NBA API calls.

    Args:
        player_id: NBA player ID
        start_date: Start date in ISO format (YYYY-MM-DD)
        end_date: End date in ISO format (YYYY-MM-DD)
        season: Season string (e.g., "2025-26")

    Returns:
        PlayerSchedule with game dates, or empty schedule if not in cache
    """
    from tools.schedule import schedule_cache

    # Look up player's team from cache
    team_id = schedule_cache.get_player_team_id(player_id, season)
    if not team_id:
        return PlayerSchedule(player_id=player_id, game_dates=[])

    # Get team schedule from cache
    dates = schedule_cache.load_team_schedule(team_id, season)
    if not dates:
        return PlayerSchedule(player_id=player_id, game_dates=[])

    # Filter by date range
    filtered = [d for d in dates if start_date <= d <= end_date]
    return PlayerSchedule(player_id=player_id, game_dates=filtered)
