"""Player API endpoints."""

import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from app.auth import yahoo_web
from app.models import (
    GameLog,
    PlayerSearchResponse,
    PlayerStats,
    PlayerStatsResponse,
    PlayerSuggestion,
    RankedPlayer,
    RankedPlayersResponse,
)

from tools.player.player_minutes_trend import (
    SuggestionResponse,
    TrendComputation,
    normalize_season_type,
    process_minute_trend_query,
)
from tools.player.player_stats import compute_player_stats
from tools.utils import player_index

router = APIRouter()

# Module-level cache for league schedule (persists across requests)
_LEAGUE_SCHEDULE_CACHE = {}


def _parse_minutes(minutes_value) -> float:
    """Parse minutes from various formats (MM:SS string or numeric)."""
    if minutes_value is None:
        return 0.0

    # If it's already a number, return it
    if isinstance(minutes_value, (int, float)):
        return float(minutes_value)

    # Convert to string and handle MM:SS format
    minutes_str = str(minutes_value).strip()
    if not minutes_str or minutes_str == "0":
        return 0.0

    # Try parsing as MM:SS format
    if ":" in minutes_str:
        try:
            parts = minutes_str.split(":")
            if len(parts) == 2:
                mins = int(parts[0])
                secs = int(parts[1])
                return mins + (secs / 60.0)
        except (ValueError, IndexError):
            pass

    # Try parsing as plain number
    try:
        return float(minutes_str)
    except ValueError:
        return 0.0


def _player_stats_to_model(stats) -> Optional[PlayerStats]:
    """Convert player stats object to Pydantic model."""
    if not stats:
        return None

    return PlayerStats(
        fg_pct=stats.fg_pct,
        ft_pct=stats.ft_pct,
        fgm=stats.fgm,
        fga=stats.fga,
        ftm=stats.ftm,
        fta=stats.fta,
        threes=stats.threes,
        points=stats.points,
        rebounds=stats.rebounds,
        assists=stats.assists,
        steals=stats.steals,
        blocks=stats.blocks,
        turnovers=stats.turnovers,
        usage_pct=stats.usage_pct,
        games_count=stats.games_count,
        games_started=stats.games_started,
        minutes=stats.minutes,
    )


def _game_to_log(game: dict, fantasy_week: Optional[int] = None) -> GameLog:
    """Convert game dict to GameLog model."""
    # Parse usage percentage (stored as decimal 0-1, display as percentage)
    usg_pct = game.get("USG_PCT", 0)
    try:
        usg_pct = float(usg_pct) if usg_pct is not None else 0.0
    except (ValueError, TypeError):
        usg_pct = 0.0

    # Calculate W/L and score from game data
    wl = None
    score = None
    home_score = game.get("home_score", 0)
    away_score = game.get("away_score", 0)
    matchup = game.get("MATCHUP", "")

    if home_score and away_score:
        # Determine if player's team is home or away based on matchup string
        # "vs XXX" means home, "@ XXX" means away
        is_home = matchup.startswith("vs ")
        if is_home:
            player_score = home_score
            opponent_score = away_score
        else:
            player_score = away_score
            opponent_score = home_score

        # Determine W/L
        if player_score > opponent_score:
            wl = "W"
        elif player_score < opponent_score:
            wl = "L"
        else:
            wl = "T"  # Tie (shouldn't happen in NBA but handle it)

        # Format score string - always show player's team score first
        score = f"{player_score}-{opponent_score}"

    return GameLog(
        date=game.get("date", ""),
        matchup=matchup,
        fantasy_week=fantasy_week,
        wl=wl,
        score=score,
        minutes=_parse_minutes(game.get("MIN", 0)),
        fg_pct=float(game.get("FG_PCT", 0)),
        ft_pct=float(game.get("FT_PCT", 0)),
        fgm=float(game.get("FGM", 0)),
        fga=float(game.get("FGA", 0)),
        ftm=float(game.get("FTM", 0)),
        fta=float(game.get("FTA", 0)),
        threes=float(game.get("FG3M", 0)),
        points=float(game.get("PTS", 0)),
        rebounds=float(game.get("REB", 0)),
        assists=float(game.get("AST", 0)),
        steals=float(game.get("STL", 0)),
        blocks=float(game.get("BLK", 0)),
        turnovers=float(game.get("TO", 0)),
        usage_pct=usg_pct,
    )


def _create_empty_game_log(
    game_date: str, matchup: str, fantasy_week: Optional[int] = None
) -> GameLog:
    """Create an empty GameLog (for DNP or future games)."""
    return GameLog(
        date=game_date,
        matchup=matchup,
        fantasy_week=fantasy_week,
        wl=None,
        score=None,
        minutes=0.0,
        fg_pct=0.0,
        ft_pct=0.0,
        fgm=0.0,
        fga=0.0,
        ftm=0.0,
        fta=0.0,
        threes=0.0,
        points=0.0,
        rebounds=0.0,
        assists=0.0,
        steals=0.0,
        blocks=0.0,
        turnovers=0.0,
        usage_pct=0.0,
    )


def _calculate_minute_trend(games: list, last_game_stats) -> float:
    """Calculate minute trend (last game vs previous 3 games average)."""
    if len(games) < 4 or not last_game_stats:
        return 0.0

    prev_3_avg = sum(_parse_minutes(g.get("MIN", 0)) for g in games[1:4]) / 3
    return last_game_stats.minutes - prev_3_avg


def _load_week_schedule(league_key: Optional[str]):
    """Load fantasy week schedule from cache or fetch if needed."""
    if not league_key:
        return None

    try:
        from tools.utils.league_cache import (
            fetch_and_cache_week_schedule,
            load_week_schedule,
        )

        week_schedule = load_week_schedule(league_key)
        if not week_schedule:
            week_schedule = fetch_and_cache_week_schedule(league_key)
        return week_schedule
    except Exception:
        return None


def _get_dnp_matchup(game_date: str, player_team_id: int, boxscore_cache) -> str:
    """Get matchup string for a DNP game."""
    try:
        date_games = boxscore_cache.load_date_boxscore(game_date)
        if not date_games:
            return "DNP"

        # Find the game where this team played
        for game_data in date_games.values():
            box_score = game_data.get("box_score", {})
            for pdata in box_score.values():
                if pdata.get("TEAM_ID") == player_team_id:
                    return pdata.get("MATCHUP", "DNP")
    except Exception:
        pass

    return "DNP"


def _fetch_recent_games(
    _player_id: int,
    player_team_id: Optional[int],
    games: list,
    today: date,
    boxscore_cache,
    week_schedule,
) -> list[GameLog]:
    """Fetch recent 4 team games (including DNP)."""
    if not player_team_id:
        return _fallback_recent_games(games, week_schedule)

    from tools.schedule import schedule_cache
    from tools.utils.league_cache import get_fantasy_week_for_date_str

    team_schedule = schedule_cache.load_team_schedule(player_team_id, "2025-26")
    if not team_schedule:
        return _fallback_recent_games(games, week_schedule)

    # Filter to past games and get last 4 (sorted desc to get most recent 4)
    past_games = [d for d in team_schedule if d < today.isoformat()]
    past_games.sort(reverse=True)
    last_4_team_games = past_games[:4]

    # Reverse to show oldest first (chronological order for display)
    last_4_team_games.reverse()

    # Map player's games by date
    player_games_by_date = {g.get("date"): g for g in games}

    recent_games = []
    for game_date in last_4_team_games:
        fantasy_week = get_fantasy_week_for_date_str(game_date, week_schedule)

        if game_date in player_games_by_date:
            # Player played - use actual stats
            game_data = player_games_by_date[game_date]
            recent_games.append(_game_to_log(game_data, fantasy_week))
        else:
            # Player didn't play - show DNP
            matchup = _get_dnp_matchup(game_date, player_team_id, boxscore_cache)
            recent_games.append(
                _create_empty_game_log(game_date, matchup, fantasy_week)
            )

    return recent_games


def _fallback_recent_games(games: list, week_schedule) -> list[GameLog]:
    """Fallback: get recent games from player's game log only."""
    if not games:
        return []

    from tools.utils.league_cache import get_fantasy_week_for_date_str

    # Sort descending to get most recent 4, then reverse for chronological display
    sorted_games = sorted(games, key=lambda g: g.get("date", ""), reverse=True)
    last_4_games = sorted_games[:4]
    last_4_games.reverse()  # Show oldest first

    recent_games = []
    for game in last_4_games:
        try:
            fantasy_week = get_fantasy_week_for_date_str(
                game.get("date", ""), week_schedule
            )
            recent_games.append(_game_to_log(game, fantasy_week))
        except Exception:
            continue

    return recent_games


def _check_today_has_boxscore(today: date, player_team_id: int, boxscore_cache) -> bool:
    """Check if today's game has been played (boxscore exists)."""
    try:
        date_games = boxscore_cache.load_date_boxscore(today.isoformat())
        if not date_games:
            return False

        # Check if this team played today
        for game_data in date_games.values():
            box_score = game_data.get("box_score", {})
            for pdata in box_score.values():
                if pdata.get("TEAM_ID") == player_team_id:
                    return True
    except Exception:
        pass

    return False


def _get_matchup_from_schedule(game_date: str, player_team_id: int) -> str:
    """Get matchup string from NBA league schedule."""
    try:
        if "2025-26" not in _LEAGUE_SCHEDULE_CACHE:
            from nba_api.stats.endpoints import scheduleleaguev2

            _LEAGUE_SCHEDULE_CACHE["2025-26"] = scheduleleaguev2.ScheduleLeagueV2(
                season="2025-26"
            ).get_data_frames()[0]

        schedule_df = _LEAGUE_SCHEDULE_CACHE["2025-26"]
        date_str = game_date.split("T")[0]

        if "gameDateNormalized" not in schedule_df.columns:
            schedule_df["gameDateNormalized"] = schedule_df["gameDateEst"].apply(
                lambda x: x.split("T")[0] if x else ""
            )

        team_games = schedule_df[
            (schedule_df["gameDateNormalized"] == date_str)
            & (
                (schedule_df["homeTeam_teamId"] == player_team_id)
                | (schedule_df["awayTeam_teamId"] == player_team_id)
            )
        ]

        if not team_games.empty:
            game = team_games.iloc[0]
            home_id = game["homeTeam_teamId"]
            away_abbr = game["awayTeam_teamTricode"]
            home_abbr = game["homeTeam_teamTricode"]
            return f"vs {away_abbr}" if home_id == player_team_id else f"@ {home_abbr}"
    except Exception:
        pass

    return "TBD"


def _fetch_upcoming_games(
    player_team_id: Optional[int], today: date, boxscore_cache, week_schedule
) -> tuple[list[GameLog], int]:
    """Fetch upcoming games from NBA schedule."""
    if not player_team_id:
        return [], 0

    from tools.schedule import schedule_cache
    from tools.utils.league_cache import get_fantasy_week_for_date_str

    team_schedule = schedule_cache.load_team_schedule(player_team_id, "2025-26")
    if not team_schedule:
        return [], 0

    # Check if today's game has been played
    today_has_boxscore = _check_today_has_boxscore(
        today, player_team_id, boxscore_cache
    )

    # If today's game has been played, start from tomorrow
    cutoff_date = (
        today.isoformat()
        if not today_has_boxscore
        else (today + timedelta(days=1)).isoformat()
    )
    future_games = [d for d in team_schedule if d >= cutoff_date]
    future_games.sort()

    upcoming_games = []
    for game_date in future_games[:4]:
        matchup_str = _get_matchup_from_schedule(game_date, player_team_id)
        fantasy_week = get_fantasy_week_for_date_str(game_date, week_schedule)
        upcoming_games.append(
            _create_empty_game_log(game_date, matchup_str, fantasy_week)
        )

    return upcoming_games, len(future_games)


@router.get("/search", response_model=PlayerSearchResponse)
def search_players(
    request: Request,
    name: str = Query(..., description="Player name to search"),
    season_type: str = Query("Regular Season", description="Season type"),
):
    """Search for players by name."""
    # Verify authentication
    yahoo_web.get_session_from_request(request)

    normalized_season = normalize_season_type(season_type)

    try:
        result = process_minute_trend_query(
            name, normalized_season, suggestion_limit=50
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to search players: {str(e)}"
        )

    if isinstance(result, SuggestionResponse):
        suggestions = [
            PlayerSuggestion(
                player_id=s["id"],
                full_name=s["full_name"],
                first_name=s.get("first_name", ""),
                last_name=s.get("last_name", ""),
            )
            for s in result.suggestions
        ]
        return PlayerSearchResponse(suggestions=suggestions, exact_match=False)

    elif isinstance(result, TrendComputation):
        # Exact match found
        suggestion = PlayerSuggestion(
            player_id=result.player_id,
            full_name=result.player_name,
            first_name="",
            last_name="",
        )
        return PlayerSearchResponse(suggestions=[suggestion], exact_match=True)

    raise HTTPException(status_code=404, detail="Player not found")


@router.get("/ranked", response_model=RankedPlayersResponse)
def get_ranked_players(
    request: Request,
    league_key: str = Query(..., description="Yahoo league key"),
    max_rank: int = Query(150, description="Maximum rank to include"),
    stats_mode: str = Query("season", description="Stats mode (last, last3, last7, season, etc.)"),
    agg_mode: str = Query("avg", description="Aggregation mode (avg, sum)"),
    ranking_mode: str = Query("yahoo", description="Ranking mode: 'yahoo' or '9cat'"),
):
    """Get all ranked players with their stats.

    Args:
        ranking_mode: 'yahoo' uses Yahoo's official rankings, '9cat' computes
                      z-scores across 9 fantasy categories and ranks by total z-score.
    """
    # Verify authentication
    yahoo_web.get_session_from_request(request)

    try:
        from tools.player.player_minutes_trend import find_player_matches
        from tools.player.player_stats import rank_players_by_zscore
        from tools.schedule.schedule_fetcher import get_season_start_date

        # Load rankings from cache
        rankings = player_index.load_rankings(league_key)
        if not rankings:
            raise HTTPException(
                status_code=404,
                detail="No rankings found. Please refresh rankings first.",
            )

        today = date.today()
        season_start = get_season_start_date("2025-26")

        # Collect all players with their stats
        players_data = []
        for player_data in rankings:
            yahoo_rank = player_data.get("rank")
            if not yahoo_rank or yahoo_rank > max_rank:
                continue

            player_name = player_data.get("name", {})
            if isinstance(player_name, dict):
                full_name = player_name.get("full", "Unknown")
            else:
                full_name = str(player_name)

            # Get team tricode from player data
            team_tricode = player_data.get("editorial_team_abbr")

            # Look up NBA API player ID by name (Yahoo IDs are different from NBA IDs)
            nba_player_id = None
            player_stats = None
            player_stats_obj = None
            try:
                nba_player_id, _ = find_player_matches(full_name, limit=1)
                if nba_player_id:
                    player_stats_obj = compute_player_stats(
                        nba_player_id, stats_mode, season_start, today, agg_mode
                    )
                    player_stats = _player_stats_to_model(player_stats_obj)
            except Exception:
                pass

            players_data.append({
                "player_id": nba_player_id or 0,
                "player_name": full_name,
                "team_tricode": team_tricode,
                "yahoo_rank": yahoo_rank,
                "stats": player_stats_obj,  # Keep raw stats for z-score calculation
                "stats_model": player_stats,
            })

        # Apply ranking based on mode
        if ranking_mode == "9cat":
            # Compute z-scores and rank by total z-score
            players_data = rank_players_by_zscore(players_data)
            ranked_players = [
                RankedPlayer(
                    player_id=p["player_id"],
                    player_name=p["player_name"],
                    team_tricode=p["team_tricode"],
                    rank=p["rank"],
                    stats=p["stats_model"],
                    z_score=round(p["z_score"], 2) if p.get("z_score") is not None else None,
                )
                for p in players_data
            ]
        else:
            # Yahoo ranking mode (default)
            players_data.sort(key=lambda p: p["yahoo_rank"])
            ranked_players = [
                RankedPlayer(
                    player_id=p["player_id"],
                    player_name=p["player_name"],
                    team_tricode=p["team_tricode"],
                    rank=p["yahoo_rank"],
                    stats=p["stats_model"],
                    z_score=None,
                )
                for p in players_data
            ]

        return RankedPlayersResponse(
            players=ranked_players,
            total_count=len(ranked_players),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch ranked players: {str(e)}"
        )


@router.get("/{player_id}", response_model=PlayerStatsResponse)
def get_player_stats(
    request: Request,
    player_id: int,
    _season_type: str = Query("Regular Season", description="Season type"),
    league_key: str = Query(
        None, description="Optional league key for fantasy week context"
    ),
):
    """Get comprehensive player statistics."""
    # Verify authentication
    yahoo_web.get_session_from_request(request)

    try:
        today = date.today()
        season_start_year = today.year if today.month >= 10 else today.year - 1
        season_start = date(season_start_year, 10, 21)
        # Derive season string (e.g., "2025-26")
        season = f"{season_start_year}-{str(season_start_year + 1)[-2:]}"

        # Compute stats for different periods
        last_game_stats = compute_player_stats(player_id, "last", season_start, today)
        last3_stats = compute_player_stats(player_id, "last3", season_start, today)
        last7_stats = compute_player_stats(player_id, "last7", season_start, today)
        season_stats = compute_player_stats(player_id, "season", season_start, today)

        # Get player data and games
        from tools.boxscore import boxscore_cache
        from tools.schedule import schedule_cache

        player_data = boxscore_cache.load_player_games(player_id, season)
        if not player_data:
            raise HTTPException(status_code=404, detail="Player not found")

        player_name = player_data.get("player_name", f"Player {player_id}")
        games = player_data.get("games", [])

        # Extract team tricode and full name from most recent game
        team_tricode = None
        if games:
            # Get most recent game (games are already sorted by date descending)
            most_recent_game = max(games, key=lambda g: g.get("date", ""), default=None)
            if most_recent_game:
                team_tricode = most_recent_game.get("teamTricode")
                # Use full name from game data if available
                first_name = most_recent_game.get("FIRST_NAME", "")
                last_name = most_recent_game.get("LAST_NAME", "")
                if first_name and last_name:
                    player_name = f"{first_name} {last_name}"

        # Calculate minute trend
        trend = _calculate_minute_trend(games, last_game_stats)

        # Load fantasy week schedule for week column
        week_schedule = _load_week_schedule(league_key)

        # Get player's team ID
        player_team_id = schedule_cache.get_player_team_id(player_id, "2025-26")

        # Fetch recent games (with DNP handling)
        recent_games = _fetch_recent_games(
            player_id, player_team_id, games, today, boxscore_cache, week_schedule
        )

        # Fetch upcoming games
        upcoming_games, total_future_games = _fetch_upcoming_games(
            player_team_id, today, boxscore_cache, week_schedule
        )

        # Get player rank from cache if league_key is provided
        # Use NBA player ID lookup which converts to name internally
        player_rank = None
        if league_key:
            player_rank = player_index.get_player_rank_by_nba_id(league_key, player_id)

        return PlayerStatsResponse(
            player_id=player_id,
            player_name=player_name,
            team_tricode=team_tricode,
            rank=player_rank,
            last_game=_player_stats_to_model(last_game_stats),
            last3=_player_stats_to_model(last3_stats),
            last7=_player_stats_to_model(last7_stats),
            season=_player_stats_to_model(season_stats),
            trend=trend,
            recent_games=recent_games,
            upcoming_games=upcoming_games,
            current_week_remaining_games=total_future_games,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch player stats: {str(e)}"
        )
