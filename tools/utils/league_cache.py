"""Cache management for league week schedules."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional


def get_league_cache_dir() -> Path:
    """Get the league cache directory."""
    cache_dir = Path.home() / ".shams" / "league"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def get_week_schedule_path(league_key: str) -> Path:
    """Get the path to the week schedule cache file for a league."""
    safe_key = league_key.replace(".", "_")
    return get_league_cache_dir() / f"{safe_key}_weeks.json"


def save_week_schedule(league_key: str, weeks: List[Dict[str, str]]) -> None:
    """Save league week schedule to cache.

    Args:
        league_key: Yahoo league key
        weeks: List of dicts with {week: int, start: YYYY-MM-DD, end: YYYY-MM-DD}
    """
    cache_path = get_week_schedule_path(league_key)
    cache_path.write_text(json.dumps(weeks, indent=2))


def load_week_schedule(league_key: str) -> Optional[List[Dict[str, str]]]:
    """Load league week schedule from cache.

    Args:
        league_key: Yahoo league key

    Returns:
        List of dicts with {week: int, start: YYYY-MM-DD, end: YYYY-MM-DD} or None if not cached
    """
    cache_path = get_week_schedule_path(league_key)
    if not cache_path.exists():
        return None

    try:
        return json.loads(cache_path.read_text())
    except (json.JSONDecodeError, IOError):
        return None


def get_fantasy_week_for_date(league_key: str, target_date: date) -> Optional[int]:
    """Get the fantasy week number for a given date.

    Args:
        league_key: Yahoo league key
        target_date: Date to look up

    Returns:
        Week number or None if date doesn't fall in any week or schedule not cached
    """
    weeks = load_week_schedule(league_key)
    if not weeks:
        return None

    target_str = target_date.isoformat()

    for week_data in weeks:
        week_start = week_data.get("start")
        week_end = week_data.get("end")

        if week_start and week_end and week_start <= target_str <= week_end:
            return week_data.get("week")

    return None


def get_fantasy_week_for_date_str(game_date: str, week_schedule) -> Optional[int]:
    """Get fantasy week number for a game date string.

    Args:
        game_date: Game date string (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
        week_schedule: Week schedule data (list of dicts with week, start, end)

    Returns:
        Week number or None if not found
    """
    if not week_schedule:
        return None

    try:
        date_str = game_date.split("T")[0]
        for week_data in week_schedule:
            start = week_data.get("start")
            end = week_data.get("end")
            if start and end and start <= date_str <= end:
                return week_data.get("week")
    except Exception:
        pass

    return None


def fetch_and_cache_week_schedule(league_key: str) -> List[Dict[str, str]]:
    """Fetch week schedule from Yahoo API and cache it.

    Args:
        league_key: Yahoo league key

    Returns:
        List of dicts with {week: int, start: YYYY-MM-DD, end: YYYY-MM-DD}
    """
    from tools.utils.yahoo import (
        extract_team_id,
        fetch_team_matchups,
        fetch_user_team_key,
    )

    team_key = fetch_user_team_key(league_key)
    team_id = extract_team_id(team_key)
    matchups = fetch_team_matchups(league_key, team_id)

    weeks = []
    for entry in matchups:
        matchup = entry.get("matchup") if isinstance(entry, dict) else entry
        if not matchup:
            continue

        try:
            week_num = int(matchup.week)
            week_start = matchup.week_start
            week_end = matchup.week_end

            weeks.append({"week": week_num, "start": week_start, "end": week_end})
        except (TypeError, ValueError, AttributeError):
            continue

    # Sort by week number
    weeks.sort(key=lambda w: w["week"])

    # Cache it
    save_week_schedule(league_key, weeks)

    return weeks


def get_league_roster_settings_path(league_key: str) -> Path:
    """Get the path to the league roster settings cache file."""
    safe_key = league_key.replace(".", "_")
    return get_league_cache_dir() / f"{safe_key}_roster.json"


def save_league_roster_settings(league_key: str, roster_positions: List[str]) -> None:
    """Save league roster position slots to cache.

    Args:
        league_key: Yahoo league key
        roster_positions: List of position slot strings (e.g., ["PG", "SG", "G", "SF", "PF", "F", "C", "Util", "Util", "BN", "BN", "IL"])
    """
    cache_path = get_league_roster_settings_path(league_key)
    data = {
        "league_key": league_key,
        "roster_positions": roster_positions,
        "cached_at": date.today().isoformat(),
    }
    cache_path.write_text(json.dumps(data, indent=2))


def load_league_roster_settings(league_key: str) -> Optional[List[str]]:
    """Load league roster position slots from cache.

    Args:
        league_key: Yahoo league key

    Returns:
        List of position slot strings or None if not cached
    """
    cache_path = get_league_roster_settings_path(league_key)
    if not cache_path.exists():
        return None

    try:
        data = json.loads(cache_path.read_text())
        return data.get("roster_positions")
    except (json.JSONDecodeError, IOError):
        return None
