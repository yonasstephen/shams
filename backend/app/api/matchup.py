"""Matchup projection API endpoints."""

import logging
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

from fastapi import APIRouter, HTTPException, Query, Request

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from app.auth import yahoo_web
from app.models import (
    AllMatchupsResponse,
    LeagueMatchup,
    MatchupProjectionResponse,
    MatchupTeam,
    PlayerContribution,
)

from tools.matchup.matchup_projection import project_league_matchups, project_matchup
from tools.utils.yahoo import YahooAuthError, fetch_user_team_key

router = APIRouter()


@router.get("", response_model=MatchupProjectionResponse)
def get_matchup_projection(
    request: Request,
    league_key: str = Query(..., description="Yahoo league key"),
    week: Optional[int] = Query(
        None, description="Week number (defaults to current week)"
    ),
    projection_mode: str = Query(
        "season", description="Projection mode: season, last3, last7, last7d, last30d"
    ),
    team_key: Optional[str] = Query(
        None, description="Team key (defaults to user's team)"
    ),
    optimize_user_roster: bool = Query(
        False, description="Optimize user's roster positions for maximum active players"
    ),
    optimize_opponent_roster: bool = Query(
        False, description="Optimize opponent's roster positions for maximum active players"
    ),
):
    """Get matchup projection for a team."""
    # Verify authentication
    yahoo_web.get_session_from_request(request)

    # Validate projection_mode
    valid_modes = ["season", "last3", "last7", "last7d", "last30d"]
    if projection_mode not in valid_modes:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid projection_mode. Must be one of: {', '.join(valid_modes)}",
        )

    try:
        # Get team key (use provided or default to user's team)
        if team_key is None:
            team_key = fetch_user_team_key(league_key)

        # Get matchup projection
        projection = project_matchup(
            league_key,
            team_key,
            week=week,
            projection_mode=projection_mode,
            optimize_user_roster=optimize_user_roster,
            optimize_opponent_roster=optimize_opponent_roster,
        )
    except YahooAuthError:
        raise HTTPException(
            status_code=401,
            detail="Authentication expired. Please refresh the page to re-authenticate.",
        )
    except Exception as e:
        logger.error("Failed to fetch matchup projection: %s", e)
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch matchup projection: {str(e)}"
        )

    try:

        user_team_data = projection.get("user_team", {})
        opponent_team_data = projection.get("opponent_team", {})

        user_team = MatchupTeam(
            team_name=user_team_data.get("team_name", "User"),
            team_key=user_team_data.get("team_key", ""),
            team_points=_extract_points(projection.get("user_team_points")),
            projected_team_points=_extract_points(
                projection.get("user_projected_team_points")
            ),
            team_ties=_extract_ties(projection.get("user_team_points")),
            projected_team_ties=_extract_ties(
                projection.get("user_projected_team_points")
            ),
        )

        opponent_team = MatchupTeam(
            team_name=opponent_team_data.get("team_name", "Opponent"),
            team_key=opponent_team_data.get("team_key", ""),
            team_points=_extract_points(projection.get("opponent_team_points")),
            projected_team_points=_extract_points(
                projection.get("opponent_projected_team_points")
            ),
            team_ties=_extract_ties(projection.get("opponent_team_points")),
            projected_team_ties=_extract_ties(
                projection.get("opponent_projected_team_points")
            ),
        )

        # Convert current player contributions (actual stats so far this week)
        current_player_contributions_list = []
        current_player_contribs = projection.get("current_player_contributions", {})
        current_player_names = projection.get("current_player_names", {})
        current_player_shooting = projection.get("current_player_shooting", {})
        current_player_ids = projection.get("current_player_ids", {})
        player_games_played = projection.get("player_games_played", {})
        player_total_games = projection.get("player_total_games", {})
        player_remaining_games = projection.get("player_remaining_games", {})
        is_on_roster_today = projection.get("is_on_roster_today", {})

        for player_key, stats in current_player_contribs.items():
            is_on_roster = is_on_roster_today.get(player_key, True)
            player_name = current_player_names.get(player_key, player_key)
            player_id = current_player_ids.get(player_key)

            contrib = PlayerContribution(
                player_key=player_key,
                player_name=player_name,
                player_id=player_id,
                total_games=player_total_games.get(player_key, 0),
                remaining_games=player_remaining_games.get(player_key, 0),
                games_played=player_games_played.get(player_key, 0),
                stats=stats,
                shooting=current_player_shooting.get(player_key, {}),
                is_on_roster_today=is_on_roster,
            )
            current_player_contributions_list.append(contrib)

        # Convert remaining player projections (projected stats for remaining games)
        player_contributions_list = []
        player_contribs = projection.get("player_contributions", {})
        player_names = projection.get("player_names", {})
        player_ids = projection.get("player_ids", {})
        player_remaining_games = projection.get("player_remaining_games", {})
        player_shooting = projection.get("player_shooting", {})

        for player_key, stats in player_contribs.items():
            is_on_roster = is_on_roster_today.get(player_key, True)
            player_name = player_names.get(player_key, player_key)
            player_id = player_ids.get(player_key)

            contrib = PlayerContribution(
                player_key=player_key,
                player_name=player_name,
                player_id=player_id,
                total_games=player_total_games.get(player_key, 0),
                remaining_games=player_remaining_games.get(player_key, 0),
                games_played=0,  # Not applicable for remaining projections
                stats=stats,
                shooting=player_shooting.get(player_key, {}),
                is_on_roster_today=is_on_roster,
            )
            player_contributions_list.append(contrib)

        # Convert opponent current player contributions (actual stats so far this week)
        opponent_current_player_contributions_list = []
        opponent_current_contribs = projection.get(
            "opponent_current_player_contributions", {}
        )
        opponent_current_names = projection.get("opponent_current_player_names", {})
        opponent_current_shooting = projection.get(
            "opponent_current_player_shooting", {}
        )
        opponent_current_ids = projection.get("opponent_current_player_ids", {})
        opponent_games_played = projection.get("opponent_player_games_played", {})
        opponent_total_games = projection.get("opponent_player_total_games", {})
        opponent_remaining_games = projection.get("opponent_player_remaining_games", {})
        opponent_is_on_roster_today = projection.get("opponent_is_on_roster_today", {})

        for player_key, stats in opponent_current_contribs.items():
            is_on_roster = opponent_is_on_roster_today.get(player_key, True)
            player_name = opponent_current_names.get(player_key, player_key)
            player_id = opponent_current_ids.get(player_key)

            contrib = PlayerContribution(
                player_key=player_key,
                player_name=player_name,
                player_id=player_id,
                total_games=opponent_total_games.get(player_key, 0),
                remaining_games=opponent_remaining_games.get(player_key, 0),
                games_played=opponent_games_played.get(player_key, 0),
                stats=stats,
                shooting=opponent_current_shooting.get(player_key, {}),
                is_on_roster_today=is_on_roster,
            )
            opponent_current_player_contributions_list.append(contrib)

        # Convert opponent remaining player projections (projected stats for remaining games)
        opponent_player_contributions_list = []
        opponent_contribs = projection.get("opponent_player_contributions", {})
        opponent_names = projection.get("opponent_player_names", {})
        opponent_ids = projection.get("opponent_player_ids", {})
        opponent_remaining_games = projection.get("opponent_player_remaining_games", {})
        opponent_shooting = projection.get("opponent_player_shooting", {})

        for player_key, stats in opponent_contribs.items():
            is_on_roster = opponent_is_on_roster_today.get(player_key, True)
            player_name = opponent_names.get(player_key, player_key)
            player_id = opponent_ids.get(player_key)

            contrib = PlayerContribution(
                player_key=player_key,
                player_name=player_name,
                player_id=player_id,
                total_games=opponent_total_games.get(player_key, 0),
                remaining_games=opponent_remaining_games.get(player_key, 0),
                games_played=0,  # Not applicable for remaining projections
                stats=stats,
                shooting=opponent_shooting.get(player_key, {}),
                is_on_roster_today=is_on_roster,
            )
            opponent_player_contributions_list.append(contrib)

        return MatchupProjectionResponse(
            week=projection.get("week", 1),
            week_start=projection.get("week_start", ""),
            week_end=projection.get("week_end", ""),
            user_team=user_team,
            opponent_team=opponent_team,
            stat_categories=projection.get("stat_categories", []),
            user_current=projection.get("user_current", {}),
            user_projection=projection.get("user_projection", {}),
            opponent_current=projection.get("opponent_current", {}),
            opponent_projection=projection.get("opponent_projection", {}),
            current_player_contributions=current_player_contributions_list,  # Roster contributions (actual stats so far)
            opponent_current_player_contributions=opponent_current_player_contributions_list,
            player_contributions=player_contributions_list,  # Remaining projections (projected stats for remaining games)
            opponent_player_contributions=opponent_player_contributions_list,
            remaining_days_projection=projection.get("remaining_days_projection", {}),
            player_positions=projection.get("player_positions", {}),
            opponent_remaining_days_projection=projection.get(
                "opponent_remaining_days_projection", {}
            ),
            opponent_player_positions=projection.get("opponent_player_positions", {}),
            projection_mode=projection_mode,
            optimize_user_roster=optimize_user_roster,
            optimize_opponent_roster=optimize_opponent_roster,
        )

    except Exception as e:
        logger.error("Failed to build matchup response: %s", e)
        raise HTTPException(
            status_code=500, detail=f"Failed to build matchup response: {str(e)}"
        )


@router.get("/all", response_model=AllMatchupsResponse)
def get_all_matchups(
    request: Request,
    league_key: str = Query(..., description="Yahoo league key"),
    week: Optional[int] = Query(
        None, description="Week number (defaults to current week)"
    ),
    projection_mode: str = Query(
        "season", description="Projection mode: season, last3, last7, last7d, last30d"
    ),
):
    """Get all matchup projections for the league."""
    # Verify authentication
    yahoo_web.get_session_from_request(request)

    # Validate projection_mode
    valid_modes = ["season", "last3", "last7", "last7d", "last30d"]
    if projection_mode not in valid_modes:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid projection_mode. Must be one of: {', '.join(valid_modes)}",
        )

    try:
        # Get user's team key
        user_team_key = fetch_user_team_key(league_key)

        # Get all matchup projections (summary only - no detailed calculations)
        result = project_league_matchups(
            league_key, projection_mode=projection_mode, summary_only=True
        )
    except YahooAuthError:
        raise HTTPException(
            status_code=401,
            detail="Authentication expired. Please refresh the page to re-authenticate.",
        )
    except Exception as e:
        logger.exception("Failed to fetch all matchups: %s", e)
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch all matchups: {str(e)}"
        )

    try:

        matchups = []
        for matchup_data in result.get("matchups", []):
            teams_data = matchup_data.get("teams", [])
            if len(teams_data) != 2:
                continue

            team_a, team_b = teams_data

            teams = [
                MatchupTeam(
                    team_name=team_a.get("team_name", "Team A"),
                    team_key=team_a.get("team_key", ""),
                    team_points=_extract_points(team_a.get("team_points")),
                    projected_team_points=_extract_points(
                        team_a.get("projected_team_points")
                    ),
                    team_ties=_extract_ties(team_a.get("team_points")),
                    projected_team_ties=_extract_ties(
                        team_a.get("projected_team_points")
                    ),
                ),
                MatchupTeam(
                    team_name=team_b.get("team_name", "Team B"),
                    team_key=team_b.get("team_key", ""),
                    team_points=_extract_points(team_b.get("team_points")),
                    projected_team_points=_extract_points(
                        team_b.get("projected_team_points")
                    ),
                    team_ties=_extract_ties(team_b.get("team_points")),
                    projected_team_ties=_extract_ties(
                        team_b.get("projected_team_points")
                    ),
                ),
            ]

            matchup = LeagueMatchup(
                week=matchup_data.get("week", week or 1),
                week_start=matchup_data.get("week_start", ""),
                week_end=matchup_data.get("week_end", ""),
                teams=teams,
                stat_categories=matchup_data.get("stat_categories", []),
            )
            matchups.append(matchup)

        return AllMatchupsResponse(
            league_name=result.get("league_name", ""),
            week=result.get("week", week or 1),
            matchups=matchups,
            user_team_key=user_team_key,
        )

    except Exception as e:
        logger.error("Failed to build all matchups response: %s", e)
        raise HTTPException(
            status_code=500, detail=f"Failed to build all matchups response: {str(e)}"
        )


def _extract_points(points_obj) -> float:
    """Extract points value from various formats."""
    if isinstance(points_obj, dict):
        return float(points_obj.get("total", 0.0))
    try:
        return float(points_obj or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _extract_ties(points_obj) -> float:
    """Extract ties value from points object."""
    if isinstance(points_obj, dict):
        return float(points_obj.get("tie", 0.0))
    return 0.0
