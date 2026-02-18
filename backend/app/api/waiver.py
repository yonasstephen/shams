"""Waiver wire API endpoints."""

import logging
import sys
from datetime import date as date_cls
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

from fastapi import APIRouter, HTTPException, Query, Request

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from app.auth import yahoo_web
from app.models import PlayerStats, WaiverPlayer, WaiverResponse

from tools.boxscore import boxscore_cache, boxscore_refresh
from tools.player.player_fetcher import clear_game_log_caches
from tools.player.player_minutes_trend import (
    TrendComputation,
    process_minute_trend_query,
)
from tools.player.player_stats import (
    _parse_stat_mode,
    compute_player_stats,
    sort_by_column,
)
from tools.schedule.schedule_fetcher import get_season_start_date
from tools.utils import player_index, waiver_cache
from tools.utils.yahoo import YahooAuthError, fetch_free_agents_and_waivers

router = APIRouter()


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


def _compute_waiver_trends(
    league_key: str,
    _refresh_cache: bool = False,
    display_count: int = 50,
    stats_mode: str = "last",
    agg_mode: str = "avg",
    sort_column: Optional[str] = None,
    sort_ascending: Optional[bool] = None,
) -> tuple[list[dict], int, Optional[dict]]:
    """Compute waiver trends and stats.

    Returns:
        Tuple of (players_data, current_week, cache_metadata)
    """
    # Clear game log caches
    clear_game_log_caches()

    # Check if box score cache needs refresh
    metadata = boxscore_cache.load_metadata()
    games_cached = metadata.get("games_cached", 0)
    cache_end_date = metadata.get("date_range", {}).get("end")

    # Auto-refresh if cache is stale
    needs_refresh = False
    if games_cached == 0:
        needs_refresh = True
    elif cache_end_date and cache_end_date != date_cls.today().isoformat():
        needs_refresh = True

    if needs_refresh:
        result = boxscore_refresh.smart_refresh()

    # Always fetch fresh players from Yahoo
    # Frontend context handles caching for navigation purposes
    players = fetch_free_agents_and_waivers(league_key)

    # Ensure all players are dictionaries
    if not all(isinstance(p, dict) for p in players):
        raise ValueError("Some players were not properly serialized to dictionaries")

    waiver_cache.save_cached_players(league_key, players)
    cache_metadata = waiver_cache.get_cache_metadata(league_key)

    # Get current week date range for games calculation
    from tools.schedule import schedule_fetcher
    from tools.utils.yahoo import (
        determine_current_week,
        extract_team_id,
        fetch_matchup_context,
        fetch_user_team_key,
    )

    week_start = None
    week_end = None
    next_week_start = None
    next_week_end = None
    current_week = 0
    try:
        team_key = fetch_user_team_key(league_key)
        team_id = extract_team_id(team_key)
        current_week = determine_current_week(league_key, team_id)
        matchup, _ = fetch_matchup_context(league_key, team_key, week=current_week)
        week_start = date_cls.fromisoformat(matchup.week_start)
        week_end = date_cls.fromisoformat(matchup.week_end)

        # Try to get next week's date range
        try:
            next_matchup, _ = fetch_matchup_context(
                league_key, team_key, week=current_week + 1
            )
            next_week_start = date_cls.fromisoformat(next_matchup.week_start)
            next_week_end = date_cls.fromisoformat(next_matchup.week_end)
        except Exception:
            # Next week might not exist (end of season)
            pass
    except Exception:
        # If we can't get week info, we'll skip games calculation
        pass

    # Build team-level back-to-back map (once for all players)
    def _build_team_back_to_back_map(season: str) -> dict:
        """Build a map of team_id -> has_back_to_back_games.

        Checks all 30 NBA teams once to see if they have games both today and tomorrow.
        Returns dict where key is team_id and value is True if team has B2B games.
        """
        from datetime import timedelta

        from nba_api.stats.static import teams

        from tools.schedule import schedule_cache

        today = date_cls.today()
        tomorrow = today + timedelta(days=1)
        today_str = today.isoformat()
        tomorrow_str = tomorrow.isoformat()

        team_b2b_map = {}
        all_teams = teams.get_teams()

        for team in all_teams:
            team_id = team.get("id")
            if not team_id:
                continue

            dates = schedule_cache.load_team_schedule(team_id, season)
            if dates:
                has_b2b = today_str in dates and tomorrow_str in dates
                team_b2b_map[team_id] = has_b2b
            else:
                team_b2b_map[team_id] = False

        return team_b2b_map

    team_b2b_map = _build_team_back_to_back_map("2025-26")

    enriched = []

    for player in players:
        name = player.get("name", {}).get("full")
        if not name:
            continue

        # Extract availability status (FA or W)
        # Note: 'availability_status' is added by our Yahoo API wrapper
        # 'status' field from Yahoo is for injury status
        status = player.get("availability_status", "FA")

        # Extract injury status and note from Yahoo data
        injury_status = player.get("status", "")
        injury_note = player.get("injury_note", "")

        try:
            result = process_minute_trend_query(
                name,
                "Regular Season",
                suggestion_limit=5,
                timeout=60,
            )
        except Exception:
            continue

        if isinstance(result, TrendComputation):
            # Compute 9-cat stats for this player
            player_stats = None
            # Get Yahoo player ID and look up NBA player ID using exact name match
            yahoo_player_id = player.get("player_id")
            nba_player_id = None
            if yahoo_player_id:
                nba_player_id = player_index.get_or_create_nba_id(yahoo_player_id, name)
            if nba_player_id:
                season_start = get_season_start_date("2025-26")
                today = date_cls.today()
                player_stats = compute_player_stats(
                    nba_player_id, stats_mode, season_start, today, agg_mode
                )

            # Calculate average minutes
            num_games, num_days = _parse_stat_mode(stats_mode)
            if num_games == 1:
                avg_minutes = result.last_minutes
            elif num_days is not None:
                # For date-based filtering, calculate average from available games
                from datetime import timedelta

                cutoff_date = date_cls.today() - timedelta(days=num_days)
                filtered_logs = []
                for log in result.logs:
                    try:
                        game_date = date_cls.fromisoformat(log[0])
                        if game_date >= cutoff_date:
                            filtered_logs.append(log)
                    except (ValueError, TypeError):
                        continue
                if filtered_logs:
                    avg_minutes = sum(log[1] for log in filtered_logs) / len(
                        filtered_logs
                    )
                else:
                    avg_minutes = result.last_minutes
            else:
                logs = result.logs
                games_to_use = logs[:num_games] if num_games else logs
                if games_to_use:
                    avg_minutes = sum(log[1] for log in games_to_use) / len(
                        games_to_use
                    )
                else:
                    avg_minutes = result.last_minutes

            # Calculate games for current week
            remaining_games = 0
            total_games = 0
            next_week_games = 0
            if week_start and week_end and nba_player_id:
                try:
                    schedule = schedule_fetcher.fetch_player_upcoming_games_from_cache(
                        nba_player_id,
                        week_start.isoformat(),
                        week_end.isoformat(),
                        "2025-26",
                    )
                    total_games = len(schedule.game_dates) if schedule.game_dates else 0
                    # Calculate remaining games (from today onwards)
                    today = date_cls.today()
                    remaining_dates = [
                        d for d in schedule.game_dates if d >= today.isoformat()
                    ]
                    remaining_games = len(remaining_dates)
                except Exception:
                    # If schedule fetch fails, just use 0
                    pass

            # Calculate games for next week
            if next_week_start and next_week_end and nba_player_id:
                try:
                    next_schedule = (
                        schedule_fetcher.fetch_player_upcoming_games_from_cache(
                            nba_player_id,
                            next_week_start.isoformat(),
                            next_week_end.isoformat(),
                            "2025-26",
                        )
                    )
                    next_week_games = (
                        len(next_schedule.game_dates) if next_schedule.game_dates else 0
                    )
                except Exception:
                    # If schedule fetch fails, just use 0
                    pass

            # Check if player's team has back-to-back games (today + tomorrow)
            has_back_to_back = False
            if nba_player_id:
                from tools.schedule import schedule_cache

                team_id = schedule_cache.get_player_team_id(nba_player_id, "2025-26")
                if team_id:
                    has_back_to_back = team_b2b_map.get(team_id, False)

            enriched.append(
                {
                    "name": name,
                    "player_id": nba_player_id,
                    "trend": result.trend,
                    "minutes": avg_minutes,
                    "status": status,
                    "injury_status": injury_status,
                    "injury_note": injury_note,
                    "stats": player_stats,
                    "last_game_date": (
                        player_stats.last_game_date if player_stats else None
                    ),
                    "remaining_games": remaining_games,
                    "total_games": total_games,
                    "next_week_games": next_week_games,
                    "has_back_to_back": has_back_to_back,
                }
            )

    # Sort players if requested
    if sort_column:
        enriched = sort_by_column(enriched, sort_column, sort_ascending)

    return enriched[:display_count], current_week, cache_metadata


@router.get("", response_model=WaiverResponse)
def get_waiver_players(
    request: Request,
    league_key: str = Query(..., description="Yahoo league key"),
    count: int = Query(50, description="Number of players to return"),
    stats_mode: str = Query("last", description="Stats mode (last, lastN, season)"),
    agg_mode: str = Query("avg", description="Aggregation mode (avg, sum)"),
    sort_column: Optional[str] = Query(None, description="Column to sort by"),
    sort_ascending: Optional[bool] = Query(None, description="Sort direction"),
    refresh: bool = Query(False, description="Force refresh cache"),
):
    """Get waiver wire players with stats."""
    # Verify authentication
    yahoo_web.get_session_from_request(request)

    try:
        players_data, current_week, cache_metadata = _compute_waiver_trends(
            league_key=league_key,
            _refresh_cache=refresh,
            display_count=count,
            stats_mode=stats_mode,
            agg_mode=agg_mode,
            sort_column=sort_column,
            sort_ascending=sort_ascending,
        )

        # Load player rankings cache to get rank for each player (by name since IDs differ between Yahoo and NBA API)
        players = [
            WaiverPlayer(
                name=p["name"],
                player_id=p.get("player_id"),
                rank=player_index.get_player_rank_by_name(league_key, p["name"]),
                trend=p["trend"],
                minutes=p["minutes"],
                status=p["status"],
                injury_status=p.get("injury_status", ""),
                injury_note=p.get("injury_note", ""),
                stats=_player_stats_to_model(p["stats"]),
                last_game_date=p.get("last_game_date"),
                remaining_games=p.get("remaining_games", 0),
                total_games=p.get("total_games", 0),
                next_week_games=p.get("next_week_games", 0),
                has_back_to_back=p.get("has_back_to_back", False),
            )
            for p in players_data
        ]

        # Format cache info for response
        cache_info = None
        if cache_metadata:
            cache_info = {
                "timestamp": cache_metadata.get("timestamp"),
                "age_hours": cache_metadata.get("age_hours"),
                "player_count": cache_metadata.get("player_count"),
            }

        return WaiverResponse(
            players=players,
            total_count=len(players),
            stats_mode=stats_mode,
            agg_mode=agg_mode,
            current_week=current_week,
            cache_info=cache_info,
        )
    except YahooAuthError as e:
        raise HTTPException(
            status_code=401,
            detail="Authentication expired. Please refresh the page to re-authenticate.",
        ) from e
    except Exception as e:
        logger.error("Failed to fetch waiver players: %s", e)
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch waiver players: {str(e)}"
        ) from e


@router.post("/refresh")
def refresh_waiver_cache(
    request: Request,
    league_key: str = Query(..., description="Yahoo league key"),
):
    """Force refresh waiver wire cache."""
    # Verify authentication
    yahoo_web.get_session_from_request(request)

    try:
        # Clear waiver cache
        waiver_cache.load_cached_players(league_key)  # Just to check it exists

        # Fetch fresh data
        players = fetch_free_agents_and_waivers(league_key)
        waiver_cache.save_cached_players(league_key, players)

        return {"message": "Cache refreshed successfully", "player_count": len(players)}
    except YahooAuthError as e:
        raise HTTPException(
            status_code=401,
            detail="Authentication expired. Please refresh the page to re-authenticate.",
        ) from e
    except Exception as e:
        logger.error("Failed to refresh cache: %s", e)
        raise HTTPException(
            status_code=500, detail=f"Failed to refresh cache: {str(e)}"
        ) from e
