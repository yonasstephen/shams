"""NBA team schedule caching and player-to-team index."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional


def get_cache_dir() -> Path:
    """Get the NBA schedule cache directory.

    Returns:
        Path to ~/.shams/nba_schedules/
    """
    cache_dir = Path.home() / ".shams" / "nba_schedules"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _get_schedules_dir(season: str) -> Path:
    """Get the schedules directory for a season."""
    schedules_dir = get_cache_dir() / "schedules" / season
    schedules_dir.mkdir(parents=True, exist_ok=True)
    return schedules_dir


def _get_player_index_dir(season: str) -> Path:
    """Get the player-to-team index directory for a season."""
    index_dir = get_cache_dir() / "player_index" / season
    index_dir.mkdir(parents=True, exist_ok=True)
    return index_dir


def save_team_schedule(team_id: int, season: str, dates: List[str]) -> None:
    """Save a team's schedule to cache.

    Args:
        team_id: NBA team ID
        season: Season string (e.g., "2025-26")
        dates: List of game dates in ISO format
    """
    schedules_dir = _get_schedules_dir(season)
    schedule_file = schedules_dir / f"{team_id}.json"

    data = {"team_id": team_id, "season": season, "dates": dates}

    try:
        with open(schedule_file, "w") as f:
            json.dump(data, f, indent=2)
    except IOError as e:
        print(f"Warning: Could not save schedule for team {team_id}: {e}")


def load_team_schedule(team_id: int, season: str) -> Optional[List[str]]:
    """Load a team's schedule from cache.

    Args:
        team_id: NBA team ID
        season: Season string (e.g., "2025-26")

    Returns:
        List of game dates or None if not cached
    """
    schedules_dir = _get_schedules_dir(season)
    schedule_file = schedules_dir / f"{team_id}.json"

    if not schedule_file.exists():
        return None

    try:
        with open(schedule_file, "r") as f:
            data = json.load(f)
        return data.get("dates", [])
    except (json.JSONDecodeError, IOError):
        return None


def save_player_team_index(player_id: int, team_id: int, season: str) -> None:
    """Save a player-to-team mapping.

    Args:
        player_id: NBA player ID
        team_id: NBA team ID
        season: Season string (e.g., "2025-26")
    """
    index_dir = _get_player_index_dir(season)
    index_file = index_dir / f"{player_id}.json"

    data = {"player_id": player_id, "team_id": team_id, "season": season}

    try:
        with open(index_file, "w") as f:
            json.dump(data, f, indent=2)
    except IOError as e:
        print(f"Warning: Could not save player-team index for {player_id}: {e}")


def get_player_team_id(player_id: int, season: str) -> Optional[int]:
    """Get a player's team ID from cache.

    Args:
        player_id: NBA player ID
        season: Season string (e.g., "2025-26")

    Returns:
        Team ID or None if not cached
    """
    index_dir = _get_player_index_dir(season)
    index_file = index_dir / f"{player_id}.json"

    if not index_file.exists():
        return None

    try:
        with open(index_file, "r") as f:
            data = json.load(f)
        return data.get("team_id")
    except (json.JSONDecodeError, IOError):
        return None


def build_player_team_index_from_boxscores(season: str) -> int:
    """Build player-to-team index by scanning boxscore cache.

    This reads through all cached games and extracts each player's most recent team.

    Args:
        season: Season string (e.g., "2025-26")

    Returns:
        Number of players indexed
    """
    from tools.boxscore import boxscore_cache

    # Get all player data from boxscore cache
    players_dir = boxscore_cache._get_players_dir(season)

    if not players_dir.exists():
        return 0

    player_teams: Dict[int, int] = {}

    for player_file in players_dir.glob("*.json"):
        try:
            with open(player_file, "r") as f:
                player_data = json.load(f)

            player_id = player_data.get("player_id")
            games = player_data.get("games", [])

            if not player_id or not games:
                continue

            # Get most recent game to find current team
            latest_game = games[-1]  # Games are sorted by date

            # Use TEAM_ID directly (it's already in the data)
            team_id = latest_game.get("TEAM_ID")

            if team_id:
                player_teams[player_id] = team_id

        except (json.JSONDecodeError, IOError, ValueError, IndexError, KeyError):
            continue

    # Save all player-team mappings
    for player_id, team_id in player_teams.items():
        save_player_team_index(player_id, team_id, season)

    return len(player_teams)


def _get_team_id_from_abbr(abbr: str) -> Optional[int]:
    """Get NBA team ID from abbreviation.

    Args:
        abbr: Team abbreviation (e.g., "LAL", "BOS")

    Returns:
        Team ID or None if not found
    """
    from nba_api.stats.static import teams

    abbr_upper = abbr.upper()
    for team in teams.get_teams():
        if team.get("abbreviation", "").upper() == abbr_upper:
            return team.get("id")

    return None


def clear_cache() -> None:
    """Clear all cached schedules and player-team index."""
    import shutil

    cache_dir = get_cache_dir()

    if cache_dir.exists():
        shutil.rmtree(cache_dir)
        print(f"✓ Cleared NBA schedule cache: {cache_dir}")
        # Recreate the directory
        cache_dir.mkdir(parents=True, exist_ok=True)


def get_cache_stats(season: str) -> Dict[str, int]:
    """Get statistics about cached data.

    Args:
        season: Season string (e.g., "2025-26")

    Returns:
        Dictionary with counts of cached teams and players
    """
    schedules_dir = _get_schedules_dir(season)
    index_dir = _get_player_index_dir(season)

    team_count = (
        len(list(schedules_dir.glob("*.json"))) if schedules_dir.exists() else 0
    )
    player_count = len(list(index_dir.glob("*.json"))) if index_dir.exists() else 0

    return {"teams_cached": team_count, "players_indexed": player_count}


def save_full_schedule(season: str, schedule_data: Dict) -> None:
    """Save full schedule data with game details.

    Args:
        season: Season string (e.g., "2025-26")
        schedule_data: Dictionary containing full schedule information including:
            - date_games: mapping of dates to game details
            - game_times: mapping of game IDs to start times
    """
    cache_dir = get_cache_dir()
    schedule_file = cache_dir / f"full_schedule_{season}.json"

    try:
        with open(schedule_file, "w") as f:
            json.dump(schedule_data, f, indent=2)
    except IOError as e:
        print(f"Warning: Could not save full schedule: {e}")


def load_full_schedule(season: str) -> Optional[Dict]:
    """Load full schedule data with game details.

    Args:
        season: Season string (e.g., "2025-26")

    Returns:
        Dictionary with schedule data or None if not cached
    """
    cache_dir = get_cache_dir()
    schedule_file = cache_dir / f"full_schedule_{season}.json"

    if not schedule_file.exists():
        return None

    try:
        with open(schedule_file, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def get_games_for_date(date_str: str, season: str) -> List[Dict]:
    """Get all games scheduled for a specific date.

    Args:
        date_str: Date in YYYY-MM-DD format
        season: Season string (e.g., "2025-26")

    Returns:
        List of game dictionaries with matchup information
    """
    schedule_data = load_full_schedule(season)

    if not schedule_data:
        return []

    date_games = schedule_data.get("date_games", {})
    return date_games.get(date_str, [])
