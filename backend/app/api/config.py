"""Config API endpoints for managing user settings."""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from tools.boxscore import boxscore_cache, boxscore_refresh
from tools.schedule import schedule_cache
from tools.schedule.game_type_settings import (
    DEFAULT_SETTINGS,
    SETTING_CATEGORIES,
    SETTING_DESCRIPTIONS,
    load_settings,
    save_settings,
)

router = APIRouter()

# Use the same config file as the CLI
CONFIG_FILE = Path.home() / ".shams" / "config.json"


class DefaultLeagueRequest(BaseModel):
    """Request body for setting default league."""

    league_key: str


class DefaultLeagueResponse(BaseModel):
    """Response for default league."""

    league_key: Optional[str] = None


class LeagueSettingsCache(BaseModel):
    """Cached league settings."""

    current_week: int
    total_weeks: int
    last_updated: str


def _ensure_config_dir():
    """Ensure the config directory exists."""
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)


def _load_config() -> dict:
    """Load configuration from file."""
    _ensure_config_dir()

    if not CONFIG_FILE.exists():
        return {}

    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def _save_config(config: dict) -> None:
    """Save configuration to file."""
    _ensure_config_dir()

    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)
    except IOError as err:
        raise HTTPException(
            status_code=500, detail=f"Failed to save config: {str(err)}"
        )


def save_league_settings(league_key: str, current_week: int, total_weeks: int) -> None:
    """Save league settings to cache.

    Args:
        league_key: Yahoo league key
        current_week: Current week number
        total_weeks: Total number of weeks in the season
    """
    config = _load_config()

    if "league_settings" not in config:
        config["league_settings"] = {}

    config["league_settings"][league_key] = {
        "current_week": current_week,
        "total_weeks": total_weeks,
        "last_updated": datetime.utcnow().isoformat(),
    }

    _save_config(config)


def load_league_settings(league_key: str) -> Optional[LeagueSettingsCache]:
    """Load cached league settings.

    Args:
        league_key: Yahoo league key

    Returns:
        LeagueSettingsCache if found, None otherwise
    """
    config = _load_config()
    league_settings = config.get("league_settings", {})

    if league_key in league_settings:
        settings_dict = league_settings[league_key]
        return LeagueSettingsCache(**settings_dict)

    return None


def clear_league_settings_cache(league_key: Optional[str] = None) -> None:
    """Clear cached league settings.

    Args:
        league_key: Specific league key to clear, or None to clear all
    """
    config = _load_config()

    if league_key:
        # Clear specific league
        if "league_settings" in config and league_key in config["league_settings"]:
            del config["league_settings"][league_key]
    else:
        # Clear all league settings
        if "league_settings" in config:
            del config["league_settings"]

    _save_config(config)


@router.get("/default-league", response_model=DefaultLeagueResponse)
def get_default_league():
    """Get the current default league key.

    Returns:
        DefaultLeagueResponse with league_key or None if not set
    """
    config = _load_config()
    league_key = config.get("default_league_key")

    return DefaultLeagueResponse(league_key=league_key)


@router.post("/default-league", response_model=DefaultLeagueResponse)
def set_default_league(body: DefaultLeagueRequest):
    """Set the default league key.

    Args:
        body: Request containing the league_key to set as default

    Returns:
        DefaultLeagueResponse with the newly set league_key
    """
    config = _load_config()
    config["default_league_key"] = body.league_key
    _save_config(config)

    return DefaultLeagueResponse(league_key=body.league_key)


@router.delete("/default-league")
def clear_default_league():
    """Clear the default league key.

    Returns:
        Success message
    """
    config = _load_config()
    config.pop("default_league_key", None)
    _save_config(config)

    return {"message": "Default league cleared"}


@router.delete("/league-settings-cache")
def clear_league_cache(league_key: Optional[str] = None):
    """Clear cached league settings.

    Args:
        league_key: Optional specific league key to clear, or None to clear all

    Returns:
        Success message
    """
    clear_league_settings_cache(league_key)

    if league_key:
        return {"message": f"League settings cache cleared for {league_key}"}
    else:
        return {"message": "All league settings cache cleared"}


class CacheStatusResponse(BaseModel):
    """Response for cache status."""

    has_cache: bool
    last_date: Optional[str] = None
    games_count: int = 0
    season: str = ""


def _compute_date_range_from_files(games_dir: Path) -> tuple[str | None, str | None]:
    """Compute date range by scanning game filenames.

    Game files are named: YYYYMMDD_gameid.json

    Returns:
        Tuple of (start_date, end_date) as ISO strings, or (None, None) if no games
    """
    min_date = None
    max_date = None

    for game_file in games_dir.glob("*.json"):
        # File format: YYYYMMDD_gameid.json
        try:
            date_str = game_file.stem.split("_")[0]
            if len(date_str) == 8 and date_str.isdigit():
                # Convert YYYYMMDD to YYYY-MM-DD
                formatted = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
                if min_date is None or formatted < min_date:
                    min_date = formatted
                if max_date is None or formatted > max_date:
                    max_date = formatted
        except (IndexError, ValueError):
            continue

    return (min_date, max_date)


@router.get("/cache-status", response_model=CacheStatusResponse)
def get_cache_status():
    """Get box score cache status.

    Returns:
        Cache status with last date, game count, and season
    """
    try:
        cache_start, cache_end = boxscore_cache.get_cached_date_range()
        metadata = boxscore_cache.load_metadata()
        _today = datetime.now()
        _year = _today.year if _today.month >= 10 else _today.year - 1
        season = metadata.get("season") or f"{_year}-{str(_year + 1)[-2:]}"

        # If metadata doesn't have date range, try to compute from files
        if not cache_end:
            # Try to detect season from game directories
            games_base_dir = boxscore_cache.get_cache_dir() / "games"
            if games_base_dir.exists():
                # Find season directories (e.g., "2024-25", "2025-26")
                season_dirs = sorted(
                    [d for d in games_base_dir.iterdir() if d.is_dir()],
                    reverse=True  # Most recent season first
                )
                for season_dir in season_dirs:
                    games_dir = season_dir
                    game_files = list(games_dir.glob("*.json"))
                    if game_files:
                        # Found games, compute date range from files
                        start_str, end_str = _compute_date_range_from_files(games_dir)
                        if end_str:
                            return CacheStatusResponse(
                                has_cache=True,
                                last_date=end_str,
                                games_count=len(game_files),
                                season=season_dir.name,
                            )

            # No game files found
            return CacheStatusResponse(has_cache=False)

        # Count actual game files instead of relying on metadata
        # (metadata counter can get out of sync)
        games_dir = boxscore_cache.get_cache_dir() / "games" / season
        if games_dir.exists():
            actual_games_count = len(list(games_dir.glob("*.json")))
        else:
            actual_games_count = metadata.get("games_cached", 0)

        return CacheStatusResponse(
            has_cache=True,
            last_date=cache_end.isoformat(),
            games_count=actual_games_count,
            season=season,
        )
    except Exception:
        return CacheStatusResponse(has_cache=False)


class SeasonInfoResponse(BaseModel):
    """Response for season information."""

    season: str
    season_start_date: str
    current_date: str
    available_seasons: list[str] = []
    cached_season: str | None = None


def _get_available_seasons() -> list[str]:
    """Get list of available NBA seasons.
    
    Returns seasons from 2020-21 to current season + 1 (for future seasons).
    """
    from datetime import date
    
    today = date.today()
    year = today.year
    month = today.month
    
    # Determine current season year
    if month >= 10:
        current_season_year = year
    else:
        current_season_year = year - 1
    
    # Generate seasons from 2020-21 to current + 1
    seasons = []
    for season_year in range(2020, current_season_year + 2):
        season_str = f"{season_year}-{str(season_year + 1)[-2:]}"
        seasons.append(season_str)
    
    # Return in reverse order (newest first)
    return list(reversed(seasons))


@router.get("/season-info", response_model=SeasonInfoResponse)
def get_season_info():
    """Get NBA season information including start date and available seasons.

    Returns:
        Season info with season string, start date, current date, and available seasons
    """
    from datetime import date

    from nba_api.stats.library.parameters import SeasonAll

    # Get cached season from metadata
    metadata = boxscore_cache.load_metadata()
    cached_season = metadata.get("season") or None

    try:
        # Get current season and start date using date-based detection
        detected_season = boxscore_refresh._detect_active_season(SeasonAll.current_season)
        season_start = boxscore_refresh.get_season_start_date(detected_season)
        today = date.today()

        return SeasonInfoResponse(
            season=detected_season,
            season_start_date=season_start.isoformat(),
            current_date=today.isoformat(),
            available_seasons=_get_available_seasons(),
            cached_season=cached_season,
        )
    except Exception:
        # Fallback to reasonable defaults
        today = date.today()
        year = today.year
        # If we're past October, use current year, otherwise previous year
        if today.month >= 10:
            season_year = year
        else:
            season_year = year - 1

        return SeasonInfoResponse(
            season=f"{season_year}-{str(season_year + 1)[-2:]}",
            season_start_date=date(season_year, 10, 21).isoformat(),
            current_date=today.isoformat(),
            available_seasons=_get_available_seasons(),
            cached_season=cached_season,
        )


class GameFileInfo(BaseModel):
    """Information about a cached game file."""

    filename: str
    game_id: str
    game_date: str
    season: str


class ScheduleFileInfo(BaseModel):
    """Information about a cached schedule file."""

    filename: str
    team_id: int
    season: str
    games_count: int


class CacheDebugResponse(BaseModel):
    """Response for cache debug information."""

    boxscore_cache: dict
    schedule_cache: dict
    metadata: dict


@router.get("/cache-debug", response_model=CacheDebugResponse)
def get_cache_debug():
    """Get comprehensive cache debug information.

    Returns:
        Detailed information about all cached data including box scores and schedules
    """
    # Scan box score cache
    boxscore_cache_dir = boxscore_cache.get_cache_dir()

    # Load metadata
    metadata = boxscore_cache.load_metadata()

    # Scan game files by season
    games_by_season = {}
    games_dir = boxscore_cache_dir / "games"
    total_games = 0

    if games_dir.exists():
        for season_dir in sorted(games_dir.iterdir()):
            if season_dir.is_dir():
                season = season_dir.name
                game_files = []

                for game_file in sorted(season_dir.glob("*.json")):
                    # Parse filename: YYYYMMDD_gameid.json
                    filename = game_file.name
                    parts = filename.replace(".json", "").split("_")
                    if len(parts) == 2:
                        date_str, game_id = parts
                        # Format date as YYYY-MM-DD
                        game_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"

                        # Load game file to get matchup info
                        matchup = None
                        home_team = None
                        away_team = None
                        home_score = None
                        away_score = None
                        box_score_data = None

                        try:
                            with open(game_file, "r") as f:
                                game_data = json.load(f)
                                matchup = game_data.get("matchup", "")
                                home_team = game_data.get("home_team", "")
                                away_team = game_data.get("away_team", "")
                                home_score = game_data.get("home_score")
                                away_score = game_data.get("away_score")
                                box_score_data = game_data.get("box_score", {})
                        except (json.JSONDecodeError, IOError):
                            pass

                        game_files.append(
                            {
                                "filename": filename,
                                "game_id": game_id,
                                "game_date": game_date,
                                "season": season,
                                "matchup": matchup,
                                "home_team": home_team,
                                "away_team": away_team,
                                "home_score": home_score,
                                "away_score": away_score,
                                "box_score": box_score_data,
                            }
                        )

                games_by_season[season] = game_files
                total_games += len(game_files)

    # Scan player index files
    players_dir = boxscore_cache_dir / "players"
    player_files = []

    if players_dir.exists():
        for player_file in sorted(players_dir.glob("*.json")):
            player_files.append(player_file.name)

    # Scan season stats files with player data
    season_stats_by_season = {}
    season_stats_dir = boxscore_cache_dir / "season_stats"

    if season_stats_dir.exists():
        for season_dir in sorted(season_stats_dir.iterdir()):
            if season_dir.is_dir():
                season = season_dir.name
                player_stats = []

                for stats_file in sorted(season_dir.glob("*.json")):
                    try:
                        with open(stats_file, "r") as f:
                            data = json.load(f)
                            player_stats.append(
                                {
                                    "filename": stats_file.name,
                                    "player_id": data.get("player_id"),
                                    "player_name": data.get("player_name", "Unknown"),
                                    "stats": data.get("stats", {}),
                                    "last_updated": data.get("last_updated"),
                                }
                            )
                    except (json.JSONDecodeError, IOError):
                        continue

                season_stats_by_season[season] = player_stats

    # Scan schedule cache
    schedule_cache_dir = schedule_cache.get_cache_dir()

    # Scan team schedule files by season
    schedules_by_season = {}
    schedules_dir = schedule_cache_dir / "schedules"
    total_schedules = 0

    if schedules_dir.exists():
        for season_dir in sorted(schedules_dir.iterdir()):
            if season_dir.is_dir():
                season = season_dir.name
                schedule_files = []

                for schedule_file in sorted(season_dir.glob("*.json")):
                    # Filename is: {team_id}.json
                    filename = schedule_file.name
                    team_id_str = filename.replace(".json", "")

                    try:
                        # Load file to get games count
                        with open(schedule_file, "r") as f:
                            data = json.load(f)
                            games_count = len(data.get("dates", []))

                        schedule_files.append(
                            {
                                "filename": filename,
                                "team_id": int(team_id_str),
                                "season": season,
                                "games_count": games_count,
                            }
                        )
                    except (json.JSONDecodeError, IOError, ValueError):
                        # Skip invalid files
                        continue

                schedules_by_season[season] = schedule_files
                total_schedules += len(schedule_files)

    # Scan player-team index files by season
    player_index_by_season = {}
    player_index_dir = schedule_cache_dir / "player_index"

    if player_index_dir.exists():
        for season_dir in sorted(player_index_dir.iterdir()):
            if season_dir.is_dir():
                season = season_dir.name
                index_files = [f.name for f in sorted(season_dir.glob("*.json"))]
                player_index_by_season[season] = index_files

    # Get cached date range
    cache_start, cache_end = boxscore_cache.get_cached_date_range()

    return CacheDebugResponse(
        boxscore_cache={
            "cache_dir": str(boxscore_cache_dir),
            "total_games": total_games,
            "total_players": len(player_files),
            "games_by_season": games_by_season,
            "player_files": player_files[:100],  # Limit to first 100 for display
            "player_files_count": len(player_files),
            "season_stats_by_season": season_stats_by_season,
            "date_range": {
                "start": cache_start.isoformat() if cache_start else None,
                "end": cache_end.isoformat() if cache_end else None,
            },
        },
        schedule_cache={
            "cache_dir": str(schedule_cache_dir),
            "total_schedules": total_schedules,
            "schedules_by_season": schedules_by_season,
            "player_index_by_season": player_index_by_season,
            "total_player_indexes": sum(
                len(files) for files in player_index_by_season.values()
            ),
        },
        metadata=metadata,
    )


# Game Type Settings Models
class GameTypeSettingsResponse(BaseModel):
    """Response for game type settings."""

    settings: dict
    descriptions: dict
    categories: dict
    defaults: dict


class GameTypeSettingsRequest(BaseModel):
    """Request body for updating game type settings."""

    settings: dict


@router.get("/game-type-settings", response_model=GameTypeSettingsResponse)
def get_game_type_settings():
    """Get current game type settings with metadata.

    Returns game type settings for filtering which NBA games count
    towards Yahoo Fantasy stats.

    Returns:
        GameTypeSettingsResponse with settings, descriptions, categories, and defaults
    """
    return GameTypeSettingsResponse(
        settings=load_settings(),
        descriptions=SETTING_DESCRIPTIONS,
        categories=SETTING_CATEGORIES,
        defaults=DEFAULT_SETTINGS,
    )


@router.post("/game-type-settings", response_model=GameTypeSettingsResponse)
def update_game_type_settings(body: GameTypeSettingsRequest):
    """Update game type settings.

    Updates which NBA game types count towards Yahoo Fantasy stats.
    Changes take effect on the next schedule refresh.

    Args:
        body: Request containing the settings dict

    Returns:
        GameTypeSettingsResponse with updated settings
    """
    # Validate settings - only accept known keys with boolean values
    new_settings = {}
    for key, value in body.settings.items():
        if key in DEFAULT_SETTINGS:
            if isinstance(value, bool):
                new_settings[key] = value
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Setting '{key}' must be a boolean value",
                )

    # Merge with existing settings (to preserve any unspecified settings)
    current_settings = load_settings()
    current_settings.update(new_settings)

    # Save settings
    if not save_settings(current_settings):
        raise HTTPException(
            status_code=500,
            detail="Failed to save game type settings",
        )

    return GameTypeSettingsResponse(
        settings=load_settings(),
        descriptions=SETTING_DESCRIPTIONS,
        categories=SETTING_CATEGORIES,
        defaults=DEFAULT_SETTINGS,
    )
