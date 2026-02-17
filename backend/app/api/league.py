"""League API endpoints."""

import logging
from datetime import date as date_cls
from datetime import datetime, timedelta
from typing import List

logger = logging.getLogger(__name__)

from app.api.config import load_league_settings, save_league_settings
from app.models import TeamScheduleDay, TeamScheduleInfo, TeamScheduleResponse
from fastapi import APIRouter, HTTPException, Request
from nba_api.stats.static import teams
from pydantic import BaseModel

from tools.schedule import schedule_cache
from tools.utils.yahoo import (
    YahooAuthError,
    determine_current_week,
    extract_team_id,
    fetch_matchup_context,
    fetch_team_matchups,
    fetch_user_team_key,
)

router = APIRouter()

# Cache expiration time in hours
CACHE_EXPIRATION_HOURS = 1


class LeagueSettingsResponse(BaseModel):
    """League settings response."""

    current_week: int
    total_weeks: int


@router.get("/{league_key}/settings", response_model=LeagueSettingsResponse)
def get_league_settings(
    request: Request, league_key: str, force_refresh: bool = False
):
    """Get league settings including current week and total weeks.

    Checks cache first and only fetches from Yahoo API if cache is missing,
    expired (older than 1 hour), or force_refresh is True.

    Args:
        request: FastAPI request object
        league_key: Yahoo league key
        force_refresh: Force refresh from Yahoo API, bypassing cache

    Returns:
        LeagueSettingsResponse with current_week and total_weeks
    """
    try:
        # Check cache first unless force_refresh is requested
        if not force_refresh:
            cached_settings = load_league_settings(league_key)
            if cached_settings:
                # Check if cache is still valid (less than 1 hour old)
                last_updated = datetime.fromisoformat(cached_settings.last_updated)
                expiration_time = last_updated + timedelta(hours=CACHE_EXPIRATION_HOURS)

                if datetime.utcnow() < expiration_time:
                    # Cache is still valid, return it
                    return LeagueSettingsResponse(
                        current_week=cached_settings.current_week,
                        total_weeks=cached_settings.total_weeks,
                    )

        # Cache miss, expired, or force refresh - fetch from Yahoo API
        # Get user's team to determine current week
        team_key = fetch_user_team_key(league_key)
        team_id = extract_team_id(team_key)

        # Determine current week
        current_week = determine_current_week(league_key, team_id)

        # Get all matchups to find max week
        matchups = fetch_team_matchups(league_key, team_id)

        # Find the highest week number
        max_week = 0
        for entry in matchups:
            matchup = entry.get("matchup") if isinstance(entry, dict) else entry
            if not matchup:
                continue
            try:
                week_value = int(matchup.week)
                if week_value > max_week:
                    max_week = week_value
            except (TypeError, ValueError, AttributeError):
                continue

        # If we couldn't determine max week, default to 23 (typical NBA fantasy season)
        total_weeks = max_week if max_week > 0 else 23

        # Save to cache
        save_league_settings(league_key, current_week, total_weeks)

        return LeagueSettingsResponse(
            current_week=current_week, total_weeks=total_weeks
        )

    except YahooAuthError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        logger.exception("Failed to fetch league settings: %s", e)
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch league settings: {str(e)}"
        )


@router.get("/{league_key}/team-schedule", response_model=TeamScheduleResponse)
def get_team_schedule(request: Request, league_key: str):
    """Get team schedules for current and next fantasy week.

    Returns all 30 NBA teams with their game schedules for the current and next
    fantasy weeks, including which dates they're playing and whether dates are in the past.

    Args:
        request: FastAPI request object
        league_key: Yahoo league key

    Returns:
        TeamScheduleResponse with team schedules
    """
    try:
        # Get user's team to determine current week
        team_key = fetch_user_team_key(league_key)
        team_id = extract_team_id(team_key)
        current_week = determine_current_week(league_key, team_id)

        # Get current week matchup for dates
        matchup, _ = fetch_matchup_context(league_key, team_key, week=current_week)
        week_start = date_cls.fromisoformat(matchup.week_start)
        week_end = date_cls.fromisoformat(matchup.week_end)

        # Get next week dates
        next_week = current_week + 1
        try:
            next_matchup, _ = fetch_matchup_context(
                league_key, team_key, week=next_week
            )
            next_week_start = date_cls.fromisoformat(next_matchup.week_start)
            next_week_end = date_cls.fromisoformat(next_matchup.week_end)
        except Exception:
            # Next week might not exist (end of season)
            # Use a week after current week as fallback
            next_week_start = week_end + timedelta(days=1)
            next_week_end = next_week_start + timedelta(days=6)

        # Get all NBA teams
        all_teams = teams.get_teams()
        season = "2025-26"
        today = date_cls.today()

        team_schedules: List[TeamScheduleInfo] = []

        for team in all_teams:
            team_id = team.get("id")
            team_name = team.get("full_name", "")
            team_abbr = team.get("abbreviation", "")

            if not team_id:
                continue

            # Load team schedule from cache
            dates = schedule_cache.load_team_schedule(team_id, season)
            if not dates:
                # No schedule cached for this team, skip
                continue

            # Generate all dates in current week
            current_week_dates: List[TeamScheduleDay] = []
            current_date = week_start
            current_week_games = 0
            current_week_total = 0

            while current_date <= week_end:
                date_str = current_date.isoformat()
                is_playing = date_str in dates
                is_past = current_date < today

                current_week_dates.append(
                    TeamScheduleDay(
                        date=date_str, is_playing=is_playing, is_past=is_past
                    )
                )

                if is_playing:
                    current_week_total += 1
                    if not is_past:
                        current_week_games += 1

                current_date += timedelta(days=1)

            # Generate all dates in next week
            next_week_dates: List[TeamScheduleDay] = []
            next_date = next_week_start
            next_week_games = 0

            while next_date <= next_week_end:
                date_str = next_date.isoformat()
                is_playing = date_str in dates
                is_past = next_date < today

                next_week_dates.append(
                    TeamScheduleDay(
                        date=date_str, is_playing=is_playing, is_past=is_past
                    )
                )

                if is_playing:
                    next_week_games += 1

                next_date += timedelta(days=1)

            team_schedules.append(
                TeamScheduleInfo(
                    team_id=team_id,
                    team_name=team_name,
                    team_abbr=team_abbr,
                    current_week_games=current_week_games,
                    current_week_total=current_week_total,
                    next_week_games=next_week_games,
                    current_week_dates=current_week_dates,
                    next_week_dates=next_week_dates,
                )
            )

        return TeamScheduleResponse(
            teams=team_schedules, current_week=current_week, next_week=next_week
        )

    except YahooAuthError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch team schedule: {str(e)}"
        )
