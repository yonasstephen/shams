"""Fetch box scores from NBA API and cache them."""

from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Dict, List, Optional

from rich.console import Console

from tools.boxscore import boxscore_cache
from tools.utils import nba_api_config  # noqa: F401  # pylint: disable=unused-import
from tools.utils.timing import TimingTracker

# Create a global console for colored output
_console = Console()

# Global progress display (set by caller)
_progress_display = None

# Global timing tracker (set by caller)
_timing_tracker: Optional[TimingTracker] = None


def set_progress_display(display) -> None:
    """Set the progress display for live updates."""
    global _progress_display
    _progress_display = display


def set_timing_tracker(tracker: Optional[TimingTracker]) -> None:
    """Set the timing tracker for latency measurements."""
    global _timing_tracker
    _timing_tracker = tracker


def _fetch_box_score_data(game_id: str):  # pylint: disable=too-many-return-statements
    """Fetch box score data from both traditional and advanced endpoints.

    Returns tuple of (player_stats_df, team_data_dict, error_info).
    - On success: (df, team_data, None)
    - On failure: (None, None, error_dict with 'type' and 'message')
    """
    from nba_api.stats.endpoints import boxscoreadvancedv3, boxscoretraditionalv3
    from requests.exceptions import ConnectionError as ConnError, RequestException, Timeout

    try:
        # Fetch traditional box score
        box_score_trad = boxscoretraditionalv3.BoxScoreTraditionalV3(game_id=game_id)

        # Check if player_stats exists and is not None
        if box_score_trad.player_stats is None:
            return (
                None,
                None,
                None,
                {"type": "empty_stats", "message": "No player stats available"},
            )

        trad_df = box_score_trad.player_stats.get_data_frame()

        if trad_df.empty:
            return None, None, None, {"type": "empty_stats", "message": "Empty player stats"}

        # Extract team data (team abbreviations and scores)
        team_data = {}
        team_scores = {}
        if box_score_trad.team_stats is not None:
            team_df = box_score_trad.team_stats.get_data_frame()
            if not team_df.empty:
                for _, team_row in team_df.iterrows():
                    team_id = team_row.get("teamId")
                    team_abbr = team_row.get(
                        "teamTricode", team_row.get("teamCity", "")
                    )
                    # Extract team score (points) - V3 API uses 'points'
                    team_pts = team_row.get("points", team_row.get("pts", 0))
                    if team_id:
                        team_data[team_id] = team_abbr
                        team_scores[team_id] = int(team_pts) if team_pts else 0

        # Fetch advanced box score for usage stats
        try:
            box_score_adv = boxscoreadvancedv3.BoxScoreAdvancedV3(game_id=game_id)

            if box_score_adv.player_stats is not None:
                adv_df = box_score_adv.player_stats.get_data_frame()

                # Merge on personId to combine traditional and advanced stats
                # Only keep usagePercentage from advanced stats
                if (
                    not adv_df.empty
                    and "personId" in adv_df.columns
                    and "usagePercentage" in adv_df.columns
                ):
                    merged_df = trad_df.merge(
                        adv_df[["personId", "usagePercentage"]],
                        on="personId",
                        how="left",
                    )
                    return merged_df, team_data, team_scores, None
        except (AttributeError, KeyError, Exception):
            # If advanced stats fail, continue with just traditional stats
            pass

        # If advanced fetch failed or no usagePercentage, add None column
        trad_df["usagePercentage"] = None
        return trad_df, team_data, team_scores, None

    except Timeout as e:
        return None, None, None, {"type": "timeout", "message": f"Request timeout: {str(e)}"}
    except ConnError as e:
        return (
            None,
            None,
            None,
            {"type": "connection_error", "message": f"Connection error: {str(e)}"},
        )
    except RequestException as e:
        return (
            None,
            None,
            None,
            {"type": "request_error", "message": f"Request failed: {str(e)}"},
        )
    except (AttributeError, KeyError) as e:
        return (
            None,
            None,
            None,
            {
                "type": "api_error",
                "message": f"API returned malformed response: {str(e)}",
            },
        )
    except Exception as e:
        return (
            None,
            None,
            None,
            {"type": "unknown_error", "message": f"Unexpected error: {str(e)}"},
        )


def fetch_box_score(
    game_id: str, game_date: Optional[str] = None
) -> tuple[Dict, Optional[Dict]]:
    """Fetch box score for a single game using V3 API.

    Args:
        game_id: NBA game ID
        game_date: Game date in YYYY-MM-DD format (optional, defaults to today)

    Returns:
        Tuple of (game_data_dict, error_info_dict)
        - On success: (game_data, None)
        - On failure: ({}, error_dict with 'type' and 'message')
    """
    try:
        player_stats_df, team_data, team_scores, error_info = _fetch_box_score_data(game_id)

        # Check if we got an error
        if error_info:
            return {}, error_info

        # Check if we got valid data
        if player_stats_df is None:
            # API returned None - game doesn't have data yet
            return {}, {"type": "no_data", "message": "Game has no data available"}

        if player_stats_df.empty:
            # Game exists but no stats yet (not played or in progress)
            return {}, {"type": "empty_stats", "message": "Game has empty stats"}

        # Team scores dictionary (might be empty if team_stats wasn't available)
        team_scores = team_scores or {}

        # V3 uses different column names - normalize to V2 format for compatibility
        # Map V3 camelCase to V2 UPPERCASE_SNAKE_CASE
        column_mapping = {
            "personId": "PLAYER_ID",
            "firstName": "FIRST_NAME",
            "familyName": "LAST_NAME",
            "nameI": "PLAYER_NAME",
            "minutes": "MIN",
            "fieldGoalsMade": "FGM",
            "fieldGoalsAttempted": "FGA",
            "fieldGoalsPercentage": "FG_PCT",
            "threePointersMade": "FG3M",
            "threePointersAttempted": "FG3A",
            "threePointersPercentage": "FG3_PCT",
            "freeThrowsMade": "FTM",
            "freeThrowsAttempted": "FTA",
            "freeThrowsPercentage": "FT_PCT",
            "reboundsOffensive": "OREB",
            "reboundsDefensive": "DREB",
            "reboundsTotal": "REB",
            "assists": "AST",
            "steals": "STL",
            "blocks": "BLK",
            "turnovers": "TO",
            "foulsPersonal": "PF",
            "points": "PTS",
            "plusMinusPoints": "PLUS_MINUS",
            "teamId": "TEAM_ID",
            "gameId": "GAME_ID",
            "usagePercentage": "USG_PCT",
            "startersBench": "STARTER_BENCH",
            "comment": "STARTER_STATUS",
        }

        # Rename columns to V2 format
        player_stats_df = player_stats_df.rename(columns=column_mapping)

        # Parse starter status - create IS_STARTER boolean
        # The V3 API orders players with starters first (5 per team), then bench players
        # We'll use this ordering to determine starters
        player_stats_df["IS_STARTER"] = 0  # Default to 0

        # Group by team and mark first 5 players per team as starters
        for team_id in player_stats_df["TEAM_ID"].unique():
            team_mask = player_stats_df["TEAM_ID"] == team_id
            team_indices = player_stats_df[team_mask].index[:5]  # First 5 players
            player_stats_df.loc[team_indices, "IS_STARTER"] = 1

        # Get game date - use provided parameter or default to today
        if game_date is None:
            game_date = date.today().isoformat()

        # Determine home/away teams
        team_ids = player_stats_df["TEAM_ID"].unique()
        home_team_id = team_ids[0] if len(team_ids) > 0 else None
        away_team_id = team_ids[1] if len(team_ids) > 1 else None

        # Get team abbreviations
        home_team_abbr = team_data.get(
            home_team_id, str(home_team_id) if home_team_id else ""
        )
        away_team_abbr = team_data.get(
            away_team_id, str(away_team_id) if away_team_id else ""
        )

        # Build box score dictionary keyed by player ID
        box_score_dict = {}
        for _, row in player_stats_df.iterrows():
            player_id = row["PLAYER_ID"]
            player_team_id = row["TEAM_ID"]

            # Construct matchup string: "vs OPP" if home, "@ OPP" if away
            matchup = ""
            if player_team_id == home_team_id and away_team_abbr:
                matchup = f"vs {away_team_abbr}"
            elif player_team_id == away_team_id and home_team_abbr:
                matchup = f"@ {home_team_abbr}"

            player_dict = row.to_dict()
            player_dict["MATCHUP"] = matchup
            box_score_dict[str(player_id)] = player_dict

        # Get team scores
        home_score = team_scores.get(home_team_id, 0) if home_team_id else 0
        away_score = team_scores.get(away_team_id, 0) if away_team_id else 0

        return {
            "game_id": game_id,
            "game_date": game_date,
            "home_team": str(home_team_id) if home_team_id else "",
            "away_team": str(away_team_id) if away_team_id else "",
            "home_score": home_score,
            "away_score": away_score,
            "box_score": box_score_dict,
        }, None

    except Exception as e:
        # Unexpected error in processing
        return {}, {
            "type": "processing_error",
            "message": f"Error processing box score: {str(e)}",
        }


def fetch_and_cache_date_range(
    start: date,
    end: date,
    date_game_ids: Dict[str, List[str]],
    season: str = "2025-26",
    game_times: Optional[Dict[str, str]] = None,
) -> tuple[int, List[Dict]]:
    """Fetch and cache box scores for a date range.

    Args:
        start: Start date
        end: End date
        date_game_ids: Mapping of dates (YYYY-MM-DD) to game IDs from schedule.
        season: Season (e.g., "2025-26")
        game_times: Optional mapping of game IDs to start times (ISO format in Eastern Time)

    Returns:
        Tuple of (number of games cached, list of failed games for logging)
    """
    import time
    from datetime import datetime

    import pytz

    total_games = 0
    failed_games = []  # Track failed games for logging (not persisted)
    current_date = start
    last_date_with_data = None  # Track the actual last date with boxscore data

    # Rate limiting: configurable via NBA_API_REQUESTS_PER_SECOND env var (default: 2.0)
    requests_per_second = float(os.getenv("NBA_API_REQUESTS_PER_SECOND", "2.0"))
    min_request_interval = 1.0 / requests_per_second if requests_per_second > 0 else 0
    last_request_time = None

    # Helper function to check if a game has started
    def has_game_started(game_id: str) -> bool:
        """Check if a game has started based on its scheduled time.

        Returns True if the game has started or if we can't determine the start time.
        """
        if not game_times or game_id not in game_times:
            # If we don't have time info, assume game might have started (conservative)
            return True

        try:
            game_time_str = game_times[game_id]
            # Parse the Eastern Time timestamp
            eastern = pytz.timezone("US/Eastern")

            # Handle the timestamp format from NBA API
            # gameDateTimeEst format: "2025-11-19T19:00:00Z" (the Z is misleading - it's actually ET, not UTC)
            # gameDateEst format: "2025-11-19T00:00:00Z" (midnight - not useful for time checking)
            if "T" in game_time_str:
                # Remove the 'Z' suffix and parse as naive datetime
                clean_time_str = game_time_str.replace("Z", "")
                game_time_naive = datetime.fromisoformat(clean_time_str)
                # Localize to Eastern Time (the API gives us Eastern Time despite the Z suffix)
                game_time = eastern.localize(game_time_naive)
            else:
                # No time component, assume midnight Eastern
                game_time = eastern.localize(
                    datetime.strptime(game_time_str, "%Y-%m-%d")
                )

            # Get current time in Eastern
            now_eastern = datetime.now(eastern)

            # Add a 30-minute buffer - only skip if game starts more than 30 min in the future
            # This accounts for timezone edge cases and gives some flexibility
            time_until_game = (game_time - now_eastern).total_seconds()
            return time_until_game <= 1800  # 30 minutes in seconds

        except Exception:
            # If we can't parse the time, assume game might have started (conservative)
            return True

    while current_date <= end:
        date_str = current_date.isoformat()

        # Start timing for this date
        if _timing_tracker:
            _timing_tracker.start(f"fetch_date_{date_str}")

        # Update status if using progress display
        if _progress_display:
            _progress_display.update_status(f"Fetching games for {date_str}...")

        # Get game IDs for this date from provided mapping
        game_ids = date_game_ids.get(date_str, [])

        if not game_ids:
            if _timing_tracker:
                _timing_tracker.end(f"fetch_date_{date_str}", f"{date_str} (no games)")
            current_date += timedelta(days=1)
            continue

        # Fetch and cache each game
        games_with_stats = 0
        games_not_started = 0
        for game_id in game_ids:
            # OPTIMIZATION: Check if the game has started before making API call
            # This uses pre-fetched schedule data to avoid unnecessary API calls
            if not has_game_started(game_id):
                # Game is scheduled in the future - skip API call entirely
                # These are NOT errors, just games that haven't happened yet
                games_not_started += 1
                continue

            # RATE LIMITING: Ensure we don't exceed the configured requests per second
            if last_request_time is not None and min_request_interval > 0:
                elapsed = time.time() - last_request_time
                if elapsed < min_request_interval:
                    sleep_time = min_request_interval - elapsed
                    time.sleep(sleep_time)

            # Record request time before making the call
            last_request_time = time.time()

            # Game should have started - fetch the box score
            game_data, error_info = fetch_box_score(game_id, game_date=date_str)

            if game_data and game_data.get("box_score"):
                # Successfully got game data
                boxscore_cache.save_game(game_id, season, date_str, game_data)
                total_games += 1
                games_with_stats += 1

                # Update last date with actual boxscore data
                if last_date_with_data is None or current_date > last_date_with_data:
                    last_date_with_data = current_date

                # Update player indexes incrementally
                box_score = game_data.get("box_score", {})
                home_score = game_data.get("home_score", 0)
                away_score = game_data.get("away_score", 0)
                for player_id_str, player_stats in box_score.items():
                    player_id = int(player_id_str)
                    player_name = player_stats.get("PLAYER_NAME", f"Player_{player_id}")

                    game_entry = {
                        "date": date_str,
                        "game_id": game_id,
                        "home_score": home_score,
                        "away_score": away_score,
                        **{
                            k: v
                            for k, v in player_stats.items()
                            if k not in ["PLAYER_NAME", "PLAYER_ID"]
                        },
                    }

                    boxscore_cache.update_player_index(
                        player_id, player_name, game_entry, season
                    )
            else:
                # ERROR: Game should have started but has no stats
                # This IS an error that should be tracked (e.g., postponed game, API issues)
                # Use the actual error information returned from fetch_box_score

                # Extract error type and message from error_info
                if error_info:
                    reason = error_info.get("type", "unknown_error")
                    error_message = error_info.get("message", "Unknown error")
                else:
                    reason = "no_data"
                    error_message = "No data returned"

                failed_games.append(
                    {
                        "game_id": game_id,
                        "date": date_str,
                        "reason": reason,
                        "error_message": error_message,
                    }
                )

        # End timing for this date
        if _timing_tracker:
            _timing_tracker.end(
                f"fetch_date_{date_str}", f"{date_str} ({games_with_stats} games)"
            )

        # Complete this step and add to display
        if _progress_display:
            total_processed = games_with_stats + games_not_started
            if total_processed > 0:
                if games_with_stats == len(game_ids):
                    # All games fetched successfully
                    msg = f"[green]✓[/green] Fetched {games_with_stats} games for {date_str}"
                elif games_not_started > 0 and games_with_stats > 0:
                    # Some games fetched, some not started
                    msg = f"[green]✓[/green] Fetched {games_with_stats} games for {date_str} [dim]({games_not_started} not started)[/dim]"
                elif games_not_started > 0 and games_with_stats == 0:
                    # No games fetched, all not started
                    msg = f"[dim]⏳[/dim] {games_not_started} games for {date_str} [dim](not started yet)[/dim]"
                else:
                    # Some games had issues (skipped)
                    skipped = len(game_ids) - games_with_stats - games_not_started
                    if skipped > 0:
                        msg = f"[yellow]✓[/yellow] Fetched {games_with_stats} games for {date_str} [dim]({skipped} skipped)[/dim]"
                    else:
                        msg = f"[green]✓[/green] Fetched {games_with_stats} games for {date_str}"
                _progress_display.complete_step(msg)

        current_date += timedelta(days=1)

    # Update season-specific metadata
    metadata = boxscore_cache.load_metadata(season)
    metadata["season"] = season
    metadata["games_cached"] = metadata.get("games_cached", 0) + total_games

    # Update date range
    existing_start = metadata.get("date_range", {}).get("start")
    existing_end = metadata.get("date_range", {}).get("end")

    if existing_start:
        metadata["date_range"]["start"] = min(start.isoformat(), existing_start)
    else:
        metadata["date_range"]["start"] = start.isoformat()

    # Only update end date if we actually fetched data
    # Use the last date with actual boxscore data, not the requested end date
    if last_date_with_data:
        if existing_end:
            metadata["date_range"]["end"] = max(
                last_date_with_data.isoformat(), existing_end
            )
        else:
            metadata["date_range"]["end"] = last_date_with_data.isoformat()
    elif not existing_end:
        # If no data was fetched and no existing end, use start date as end
        metadata["date_range"]["end"] = start.isoformat()
    # If no data was fetched but existing_end exists, keep the existing end date

    metadata["last_updated"] = datetime.now().isoformat()

    boxscore_cache.save_metadata(metadata, season)

    return total_games, failed_games
