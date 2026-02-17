"""Helpers for fetching player data and stats via nba_api."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from typing import Dict, Iterable, List, Optional

from nba_api.stats.endpoints import playercareerstats

from tools.utils import nba_api_config  # noqa: F401 - Configure NBA API timeout


@dataclass
class PlayerAverages:
    player_id: int
    stats: dict


@dataclass
class PlayerShootingStats:
    """Shooting stats with makes and attempts."""

    fgm: float
    fga: float
    fg_pct: float
    ftm: float
    fta: float
    ft_pct: float


def clear_game_log_caches() -> None:
    """Clear all game log and shooting stat caches to get fresh data.

    Call this to ensure minute trends and shooting stats reflect the latest games.
    """
    fetch_player_team_id.cache_clear()


def _latest_season_code(seasons: Iterable[str]) -> Optional[str]:
    latest = None
    for entry in seasons:
        try:
            start = int(entry[:4])
        except (ValueError, TypeError):
            continue
        if latest is None or start > latest:
            latest = start
    return None if latest is None else f"{latest}-{str(latest + 1)[-2:]}"


@lru_cache(maxsize=512)
def _team_abbr_map() -> Dict[str, int]:
    from nba_api.stats.static import teams

    mapping: Dict[str, int] = {}
    for team in teams.get_teams():
        abbr = team.get("abbreviation", "").upper()
        if abbr:
            mapping[abbr] = team.get("id")
    return mapping


@lru_cache(maxsize=512)
def player_id_lookup(full_name: str) -> Optional[int]:
    """Look up a player's NBA ID by full name.

    Args:
        full_name: Player's full name

    Returns:
        NBA player ID or None if not found
    """
    from nba_api.stats.static import players

    name_lower = full_name.lower()
    for player in players.get_players():
        if player["full_name"].lower() == name_lower:
            return player["id"]

    # fallback fuzzy match using existing logic from player_minutes_trend
    from tools.player.player_minutes_trend import find_player_matches

    resolved_id, suggestions = find_player_matches(full_name, limit=1)
    if resolved_id:
        return resolved_id
    if suggestions:
        try:
            return int(suggestions[0]["id"])  # type: ignore[index]
        except (KeyError, ValueError, TypeError):
            return None
    return None


@lru_cache(maxsize=512)
def fetch_player_team_id(player_id: int) -> Optional[int]:
    """Fetch the team ID for a player.

    Args:
        player_id: NBA player ID

    Returns:
        Team ID or None if not found
    """
    career = playercareerstats.PlayerCareerStats(player_id=player_id)
    df = career.get_data_frames()[0]
    if df.empty:
        return None
    latest_row = df.iloc[-1]
    team_id = latest_row.get("TEAM_ID")
    try:
        team_id = int(team_id)
        if team_id:
            return team_id
    except (TypeError, ValueError):
        pass

    team_abbr = latest_row.get("TEAM_ABBREVIATION")
    if isinstance(team_abbr, str):
        return _team_abbr_map().get(team_abbr.upper())
    return None


def fetch_player_stats_from_cache(
    player_id: int, start: date, end: date, season: Optional[str] = None
) -> List[Dict]:
    """Fetch player stats from box score cache.

    Args:
        player_id: NBA player ID
        start: Start date
        end: End date
        season: Season string (e.g., "2025-26"). If None, uses legacy location.

    Returns:
        List of game stat dictionaries
    """
    from tools.boxscore import boxscore_cache

    # Load player data from cache
    player_data = boxscore_cache.load_player_games(player_id, season)

    if not player_data:
        return []

    games = player_data.get("games", [])

    # Filter by date range
    filtered_games = []
    for game in games:
        game_date_str = game.get("date", "")
        try:
            game_date = date.fromisoformat(game_date_str)
            if start <= game_date <= end:
                filtered_games.append(game)
        except (ValueError, TypeError):
            continue

    return filtered_games


def fetch_player_shooting_averages_from_cache(
    player_id: int, season: Optional[str] = None
) -> Optional[PlayerShootingStats]:
    """Fetch player shooting averages from the local cache.

    Args:
        player_id: NBA player ID
        season: Season string (defaults to current season)

    Returns:
        PlayerShootingStats object or None if not cached
    """
    from nba_api.stats.library.parameters import SeasonAll

    from tools.boxscore import boxscore_cache

    season_code = season or SeasonAll.current_season

    stats = boxscore_cache.load_player_season_stats(player_id, season_code)
    if not stats:
        return None

    return PlayerShootingStats(
        fgm=stats.get("fgm", 0.0),
        fga=stats.get("fga", 0.0),
        fg_pct=stats.get("fg_pct", 0.0),
        ftm=stats.get("ftm", 0.0),
        fta=stats.get("fta", 0.0),
        ft_pct=stats.get("ft_pct", 0.0),
    )
