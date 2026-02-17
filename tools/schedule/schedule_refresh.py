"""Schedule caching orchestration for fetching and storing NBA team schedules."""

from __future__ import annotations

from typing import Dict, List, Optional

from rich.console import Console

from tools.schedule.game_type_settings import is_fantasy_eligible_game, load_settings
from tools.utils.api_retry import retry_with_backoff
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


@retry_with_backoff(max_retries=3, base_delay=2.0, max_delay=10.0)
def _fetch_league_schedule(season: str):
    """Fetch the entire NBA league schedule with retry logic."""
    from nba_api.stats.endpoints import scheduleleaguev2

    schedule = scheduleleaguev2.ScheduleLeagueV2(season=season)
    return schedule.get_data_frames()[0]


def cache_all_team_schedules(
    season: str,
) -> tuple[Dict[str, List[str]], Dict[str, str]]:
    """Fetch and cache all NBA team schedules efficiently.

    Fetches the entire league schedule ONCE and parses it for all 30 teams,
    instead of making 30 separate API calls.

    Args:
        season: Season string (e.g., "2025-26")

    Returns:
        Tuple of:
        - Dictionary mapping dates (YYYY-MM-DD) to lists of game IDs
        - Dictionary mapping game IDs to game start times (ISO format in Eastern Time)
    """
    from nba_api.stats.static import teams

    from tools.schedule import schedule_cache

    # Start timing
    if _timing_tracker:
        _timing_tracker.start("schedule_fetch")

    # Fetch ENTIRE league schedule ONCE (not 30 times!) with retry logic
    if _progress_display:
        _progress_display.update_status("Fetching NBA team schedules...")

    try:
        df = _fetch_league_schedule(season)
    except Exception as e:
        msg = f"[red]✗[/red] Failed to fetch league schedule after retries: {e}"
        if _progress_display:
            _progress_display.add_line(msg)
        else:
            _console.print(msg)
        if _timing_tracker:
            _timing_tracker.end("schedule_fetch")
        return {}, {}

    if df.empty:
        msg = "[red]✗[/red] No schedule data available"
        if _progress_display:
            _progress_display.add_line(msg)
        else:
            _console.print(msg)
        if _timing_tracker:
            _timing_tracker.end("schedule_fetch")
        return {}, {}

    # Parse schedule for all teams in one pass (new format only)
    team_schedules = {}  # team_id -> list of dates
    date_game_ids = {}  # date -> list of game_ids
    game_times = {}  # game_id -> game start time (ISO format)
    date_games = {}  # date -> list of game details
    all_teams = teams.get_teams()

    # Build team ID to name/abbreviation mapping
    team_info = {team["id"]: team for team in all_teams}

    # Load game type settings for filtering
    game_type_settings = load_settings()
    games_filtered = 0
    games_included = 0

    for _, row in df.iterrows():
        # Filter out games that don't count towards fantasy based on settings
        if not is_fantasy_eligible_game(row, game_type_settings):
            games_filtered += 1
            continue

        games_included += 1
        home_id = row.get("homeTeam_teamId")
        away_id = row.get("awayTeam_teamId")
        game_date_est = row.get("gameDateEst", "")
        game_date_time_est = row.get(
            "gameDateTimeEst", ""
        )  # Full timestamp with actual time
        game_id = row.get("gameId", "")

        if game_date_est:
            date_str = game_date_est.split("T")[0]
            if home_id:
                team_schedules.setdefault(home_id, []).append(date_str)
            if away_id:
                team_schedules.setdefault(away_id, []).append(date_str)

            # Build date -> game_ids mapping and store game times
            if game_id:
                date_game_ids.setdefault(date_str, []).append(str(game_id))
                # Store the full ISO timestamp with actual game time (use gameDateTimeEst, not gameDateEst)
                # gameDateTimeEst includes the actual tip-off time (e.g., 19:00:00 for 7pm ET)
                # gameDateEst is always midnight (00:00:00) which is incorrect for checking if game started
                game_time = game_date_time_est if game_date_time_est else game_date_est
                game_times[str(game_id)] = game_time

                # Build game details for this date
                home_team_info = team_info.get(home_id, {})
                away_team_info = team_info.get(away_id, {})

                game_detail = {
                    "game_id": str(game_id),
                    "game_datetime": game_time,  # Full datetime with actual tip-off time in Eastern Time
                    "home_team": home_id,
                    "away_team": away_id,
                    "home_team_name": home_team_info.get("full_name", ""),
                    "away_team_name": away_team_info.get("full_name", ""),
                    "home_team_tricode": home_team_info.get("abbreviation", ""),
                    "away_team_tricode": away_team_info.get("abbreviation", ""),
                    "postponed_status": row.get("postponedStatus", "N"),  # Y = postponed, N = normal
                }

                date_games.setdefault(date_str, []).append(game_detail)

    # Save schedules for all teams
    teams_cached = 0
    for team in all_teams:
        team_id = team["id"]
        dates = team_schedules.get(team_id, [])
        if dates:
            schedule_cache.save_team_schedule(team_id, season, dates)
            teams_cached += 1

    # Save full schedule data with game details
    schedule_cache.save_full_schedule(
        season, {"date_games": date_games, "game_times": game_times, "season": season}
    )

    # End timing
    if _timing_tracker:
        _timing_tracker.end("schedule_fetch")

    msg = f"[green]✓[/green] Cached schedules for {teams_cached} teams ({games_included} games, {games_filtered} filtered)"
    if _progress_display:
        _progress_display.complete_step(msg)
    else:
        _console.print(msg)

    return date_game_ids, game_times
