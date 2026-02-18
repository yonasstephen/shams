"""Box score API endpoints."""

import json
import sys
from datetime import date as date_cls
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from app.auth import yahoo_web

from tools.boxscore import boxscore_cache
from tools.schedule import schedule_cache

router = APIRouter()


def get_team_name_from_id(team_id: int) -> Optional[str]:
    """Get team full name from team ID using nba_api."""
    try:
        from nba_api.stats.static import teams

        all_teams = teams.get_teams()
        for team in all_teams:
            if team.get("id") == team_id:
                return team.get("full_name", team.get("nickname", ""))
        return None
    except Exception:
        return None


class BoxScoreDate(BaseModel):
    """Date with game count."""

    date: str
    game_count: int


class LatestDateResponse(BaseModel):
    """Latest date with games."""

    date: str
    season: str


class PlayerBoxScore(BaseModel):
    """Player box score stats."""

    PLAYER_ID: int
    PLAYER_NAME: str
    TEAM_ID: int
    teamTricode: Optional[str] = None
    MIN: Optional[str] = None
    FGM: Optional[int] = None
    FGA: Optional[int] = None
    FG_PCT: Optional[float] = None
    FG3M: Optional[int] = None
    FG3A: Optional[int] = None
    FG3_PCT: Optional[float] = None
    FTM: Optional[int] = None
    FTA: Optional[int] = None
    FT_PCT: Optional[float] = None
    OREB: Optional[int] = None
    DREB: Optional[int] = None
    REB: Optional[int] = None
    AST: Optional[int] = None
    STL: Optional[int] = None
    BLK: Optional[int] = None
    TO: Optional[int] = None
    PF: Optional[int] = None
    PTS: Optional[int] = None
    PLUS_MINUS: Optional[int] = None


class GameBoxScore(BaseModel):
    """Full game box score."""

    game_id: str
    game_date: str
    season: str
    matchup: Optional[str] = None
    home_team: Optional[int] = None
    away_team: Optional[int] = None
    home_team_name: Optional[str] = None
    away_team_name: Optional[str] = None
    home_team_tricode: Optional[str] = None
    away_team_tricode: Optional[str] = None
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    box_score: Dict[str, Any]  # player_id -> stats
    is_scheduled: bool = False  # True for future games from schedule
    game_time: Optional[str] = None  # Game start time for scheduled games
    postponed_status: Optional[str] = None  # Y = postponed, N = normal


# Player Insights Models (for on-demand play-by-play analysis)
class PlayerInsight(BaseModel):
    """Individual insight about player performance."""

    type: str  # "foul_trouble", "scoring_streak", "limited_minutes", etc.
    severity: str  # "info", "warning", "critical"
    message: str  # Human-readable message
    details: Optional[Dict[str, Any]] = None  # Additional context


class QuarterBreakdown(BaseModel):
    """Player stats breakdown by quarter."""

    quarter: int  # 1, 2, 3, 4, or 5+ for OT
    quarter_label: str  # "Q1", "Q2", "Q3", "Q4", "OT1", etc.
    minutes: float
    points: int
    fouls: int
    field_goals_made: int
    field_goals_attempted: int
    three_pointers_made: int
    three_pointers_attempted: int
    free_throws_made: int
    free_throws_attempted: int
    rebounds: int
    assists: int
    steals: int
    blocks: int
    turnovers: int


class FoulEvent(BaseModel):
    """Individual foul event."""

    quarter: int
    time_remaining: str  # "10:30" format
    foul_number: int  # 1st, 2nd, 3rd foul, etc.
    foul_type: str  # "personal", "offensive", "technical", etc.
    elapsed_minutes: float  # Minutes into the game when foul occurred


class SubstitutionEvent(BaseModel):
    """Substitution event (player entering or leaving game)."""

    quarter: int
    time_remaining: str
    event_type: str  # "in" or "out"
    elapsed_minutes: float


class PlayerInsightsResponse(BaseModel):
    """Full response for player performance insights."""

    player_id: int
    player_name: str
    game_id: str
    total_minutes: float
    insights: List[PlayerInsight]
    quarter_breakdown: List[QuarterBreakdown]
    foul_timeline: List[FoulEvent]
    substitution_timeline: List[SubstitutionEvent]


@router.get("/dates", response_model=List[BoxScoreDate])
def get_boxscore_dates(request: Request):
    """Get all dates with cached games and scheduled games.

    Returns:
        List of dates with game counts, sorted by date descending
    """
    # Verify authentication
    yahoo_web.get_session_from_request(request)

    try:
        # Get metadata to find current season
        metadata = boxscore_cache.load_metadata()
        season = metadata.get("season", "2025-26")

        # Parse all game files to extract dates and track game IDs
        date_counts: Dict[str, int] = {}
        date_game_ids: Dict[str, set] = {}  # Track which games have boxscores per date

        # Get games directory for current season
        games_dir = boxscore_cache._get_games_dir(season)

        if games_dir.exists():
            for game_file in games_dir.glob("*.json"):
                # Filename format: YYYYMMDD_gameid.json
                filename = game_file.name
                parts = filename.replace(".json", "").split("_")

                if len(parts) >= 2:
                    date_part = parts[0]
                    game_id = "_".join(parts[1:])  # Handle game IDs with underscores

                    if len(date_part) == 8 and date_part.isdigit():
                        # Format as YYYY-MM-DD
                        formatted_date = f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:]}"

                        # Track game IDs for this date
                        if formatted_date not in date_game_ids:
                            date_game_ids[formatted_date] = set()
                        date_game_ids[formatted_date].add(game_id)

                        date_counts[formatted_date] = date_counts.get(formatted_date, 0) + 1

        # Also add dates from schedule cache and merge counts
        schedule_data = schedule_cache.load_full_schedule(season)
        if schedule_data:
            date_games = schedule_data.get("date_games", {})
            for date_str, games_list in date_games.items():
                # Count scheduled games that don't have boxscores yet
                scheduled_without_boxscore = 0
                existing_game_ids = date_game_ids.get(date_str, set())

                for game in games_list:
                    game_id = game.get("game_id", "")
                    if game_id not in existing_game_ids:
                        scheduled_without_boxscore += 1

                # Add scheduled games to the count
                if date_str in date_counts:
                    # Date has some boxscores, add scheduled games without boxscores
                    date_counts[date_str] += scheduled_without_boxscore
                else:
                    # Date only has scheduled games, no boxscores yet
                    date_counts[date_str] = len(games_list)

        # Convert to list and sort by date descending
        dates = [
            BoxScoreDate(date=date_str, game_count=count)
            for date_str, count in date_counts.items()
        ]
        dates.sort(key=lambda x: x.date, reverse=True)

        return dates

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get dates: {str(e)}") from e


@router.get("/latest-date", response_model=LatestDateResponse)
def get_latest_date(request: Request):
    """Get the most recent date with cached games.

    Returns:
        Latest date and season
    """
    # Verify authentication
    yahoo_web.get_session_from_request(request)

    try:
        # Get all dates
        dates_response = get_boxscore_dates(request)

        if not dates_response:
            raise HTTPException(status_code=404, detail="No cached games found")

        # Get metadata for season
        metadata = boxscore_cache.load_metadata()
        season = metadata.get("season", "2025-26")

        # First date is the latest (sorted descending)
        latest_date = dates_response[0].date

        return LatestDateResponse(date=latest_date, season=season)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get latest date: {str(e)}"
        ) from e


@router.get("/games/{date}", response_model=List[GameBoxScore])
def get_games_for_date(request: Request, date: str):
    """Get all games for a specific date.

    Args:
        date: Date in YYYY-MM-DD format

    Returns:
        List of games with full box scores (past games) and scheduled games (future games)
    """
    # Verify authentication
    yahoo_web.get_session_from_request(request)

    try:
        # Validate date format
        try:
            date_cls.fromisoformat(date)
        except ValueError as e:
            raise HTTPException(
                status_code=400, detail="Invalid date format. Use YYYY-MM-DD"
            ) from e

        # Get metadata to find current season
        metadata = boxscore_cache.load_metadata()
        season = metadata.get("season", "2025-26")

        # Get games directory for current season
        games_dir = boxscore_cache._get_games_dir(season)

        # Track game IDs that have box scores
        games_with_boxscores = set()
        games = []

        # First, try to get games from box score cache (past/completed games)
        if games_dir.exists():
            # Convert date to filename format (YYYYMMDD)
            date_prefix = date.replace("-", "")

            # Find all game files for this date
            for game_file in sorted(games_dir.glob(f"{date_prefix}_*.json")):
                try:
                    with open(game_file, "r", encoding="utf-8") as f:
                        game_data = json.load(f)

                    game_id = game_data.get("game_id", "")
                    games_with_boxscores.add(game_id)

                    # Extract team tricodes and calculate scores from box score
                    box_score = game_data.get("box_score", {})
                    home_team_id_str = game_data.get("home_team", "")
                    away_team_id_str = game_data.get("away_team", "")

                    # Convert team IDs to integers (they're stored as strings)
                    try:
                        home_team_id = (
                            int(home_team_id_str) if home_team_id_str else None
                        )
                        away_team_id = (
                            int(away_team_id_str) if away_team_id_str else None
                        )
                    except (ValueError, TypeError):
                        home_team_id = None
                        away_team_id = None

                    home_tricode = None
                    away_tricode = None
                    home_score = 0
                    away_score = 0

                    # Find team tricodes and calculate scores from player data
                    for player_stats in box_score.values():
                        team_id = player_stats.get("TEAM_ID")
                        tricode = player_stats.get("teamTricode")
                        pts = player_stats.get("PTS", 0) or 0

                        if team_id == home_team_id:
                            home_tricode = tricode
                            home_score += int(pts)
                        elif team_id == away_team_id:
                            away_tricode = tricode
                            away_score += int(pts)

                    # Get team names
                    home_team_name = (
                        get_team_name_from_id(home_team_id) if home_team_id else None
                    )
                    away_team_name = (
                        get_team_name_from_id(away_team_id) if away_team_id else None
                    )

                    # Use stored scores if available, otherwise use calculated
                    # (game files don't store scores, so we always use calculated)
                    stored_home_score = game_data.get("home_score")
                    stored_away_score = game_data.get("away_score")

                    game_box_score = GameBoxScore(
                        game_id=game_id,
                        game_date=game_data.get("game_date", date),
                        season=season,
                        matchup=game_data.get("matchup"),
                        home_team=home_team_id,
                        away_team=away_team_id,
                        home_team_name=home_team_name,
                        away_team_name=away_team_name,
                        home_team_tricode=home_tricode,
                        away_team_tricode=away_tricode,
                        home_score=(
                            stored_home_score
                            if stored_home_score is not None
                            else home_score
                        ),
                        away_score=(
                            stored_away_score
                            if stored_away_score is not None
                            else away_score
                        ),
                        box_score=box_score,
                        is_scheduled=False,
                        postponed_status="N",  # Games with box scores are not postponed
                    )

                    games.append(game_box_score)

                except (json.JSONDecodeError, IOError):
                    # Skip invalid game files
                    continue

        # Now check for scheduled games from the schedule cache (future games or games without box scores yet)
        scheduled_games = schedule_cache.get_games_for_date(date, season)
        for scheduled_game in scheduled_games:
            game_id = scheduled_game.get("game_id", "")

            # Only add if we don't already have a box score for this game
            if game_id not in games_with_boxscores:
                # Extract date from game_datetime if available
                game_datetime = scheduled_game.get("game_datetime", "")

                game_box_score = GameBoxScore(
                    game_id=game_id,
                    game_date=date,
                    season=season,
                    home_team=scheduled_game.get("home_team"),
                    away_team=scheduled_game.get("away_team"),
                    home_team_name=scheduled_game.get("home_team_name"),
                    away_team_name=scheduled_game.get("away_team_name"),
                    home_team_tricode=scheduled_game.get("home_team_tricode"),
                    away_team_tricode=scheduled_game.get("away_team_tricode"),
                    box_score={},  # Empty box score for scheduled games
                    is_scheduled=True,
                    game_time=game_datetime,  # Full datetime with tip-off time
                    postponed_status=scheduled_game.get("postponed_status", "N"),
                )

                games.append(game_box_score)

        return games

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get games: {str(e)}") from e


@router.get(
    "/player-insights/{game_id}/{player_id}",
    response_model=PlayerInsightsResponse,
)
def get_player_insights(request: Request, game_id: str, player_id: int):
    """Get performance insights for a player in a specific game.

    This endpoint fetches play-by-play data on-demand to analyze a player's
    performance, including foul trouble detection, minutes distribution,
    and other insights.

    Args:
        game_id: NBA game ID (e.g., "0022400123")
        player_id: NBA player ID

    Returns:
        PlayerInsightsResponse with detailed performance insights
    """
    # Verify authentication
    yahoo_web.get_session_from_request(request)

    try:
        from tools.boxscore import player_insights

        # Analyze player performance
        insights_data = player_insights.analyze_player_performance(
            game_id=game_id,
            player_id=player_id,
        )

        if not insights_data:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"Play-by-play data not available for game {game_id}. "
                    "This may be an older game or the data is not yet available."
                ),
            )

        # Convert dataclass to response model
        return PlayerInsightsResponse(
            player_id=insights_data.player_id,
            player_name=insights_data.player_name,
            game_id=insights_data.game_id,
            total_minutes=insights_data.total_minutes,
            insights=[
                PlayerInsight(
                    type=i.type,
                    severity=i.severity,
                    message=i.message,
                    details=i.details,
                )
                for i in insights_data.insights
            ],
            quarter_breakdown=[
                QuarterBreakdown(
                    quarter=q.quarter,
                    quarter_label=q.quarter_label,
                    minutes=q.minutes,
                    points=q.points,
                    fouls=q.fouls,
                    field_goals_made=q.field_goals_made,
                    field_goals_attempted=q.field_goals_attempted,
                    three_pointers_made=q.three_pointers_made,
                    three_pointers_attempted=q.three_pointers_attempted,
                    free_throws_made=q.free_throws_made,
                    free_throws_attempted=q.free_throws_attempted,
                    rebounds=q.rebounds,
                    assists=q.assists,
                    steals=q.steals,
                    blocks=q.blocks,
                    turnovers=q.turnovers,
                )
                for q in insights_data.quarter_breakdown
            ],
            foul_timeline=[
                FoulEvent(
                    quarter=f.quarter,
                    time_remaining=f.time_remaining,
                    foul_number=f.foul_number,
                    foul_type=f.foul_type,
                    elapsed_minutes=f.elapsed_minutes,
                )
                for f in insights_data.foul_timeline
            ],
            substitution_timeline=[
                SubstitutionEvent(
                    quarter=s.quarter,
                    time_remaining=s.time_remaining,
                    event_type=s.event_type,
                    elapsed_minutes=s.elapsed_minutes,
                )
                for s in insights_data.substitution_timeline
            ],
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to analyze player performance: {str(e)}",
        ) from e
