"""Box score refresh logic and orchestration."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, Optional

from nba_api.stats.library.parameters import SeasonAll
from rich.console import Console

from tools.boxscore import boxscore_cache, boxscore_fetcher
from tools.schedule import schedule_cache, schedule_refresh
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


def _detect_active_season(_current_season: str) -> str:
    """Detect which season should be used based on the current date.

    Uses date-based logic to determine the active NBA season.
    The NBA season runs from October to June:
    - If we're between October and December, we're in the first year of the season
    - If we're between January and June, we're in the second year of the season
    - If we're between July and September, we're in the off-season (use previous season)

    Args:
        current_season: Season string from SeasonAll.current_season (e.g., "2025-26")

    Returns:
        Season string for the active season
    """
    today = date.today()
    current_year = today.year
    current_month = today.month

    # Determine the season based on current date
    # NBA regular season: October - April
    # NBA playoffs: April - June
    # Off-season: July - September
    if current_month >= 10:
        # October-December: we're in the first year of the season (e.g., Oct 2025 = 2025-26)
        season_start_year = current_year
    elif current_month <= 6:
        # January-June: we're in the second year of the season (e.g., Jan 2026 = 2025-26)
        season_start_year = current_year - 1
    else:
        # July-September (off-season): use the season that just ended
        season_start_year = current_year - 1

    # Format season string (e.g., 2025 -> "2025-26")
    season_end_suffix = str(season_start_year + 1)[-2:]
    detected_season = f"{season_start_year}-{season_end_suffix}"

    return detected_season


def get_season_start_date(season: Optional[str] = None) -> date:
    """Get the start date of the NBA season.

    Auto-detects the active season and calculates its start date.

    Args:
        season: Optional season string (e.g., "2025-26"). If None, auto-detects active season.

    Returns:
        Season start date (typically October 21 of the first year)
    """
    # Determine which season to use
    if season is None:
        season = _detect_active_season(SeasonAll.current_season)

    # Parse season (format: "2025-26")
    try:
        year = int(season.split("-")[0])
        # NBA season typically starts on October 21 of the first year
        # For "2025-26", that's October 21, 2025
        return date(year, 10, 21)
    except (ValueError, IndexError):
        # Fallback to today minus 7 days
        return date.today() - timedelta(days=7)


def refresh_boxscores(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    season: Optional[str] = None,
) -> Dict:
    """Refresh box scores for a date range.

    Args:
        start_date: Start date (defaults to season start date)
        end_date: End date (defaults to today)
        season: Season (defaults to auto-detected active season)

    Returns:
        Summary dictionary with games_fetched and players_updated
    """
    if season is None:
        current_season = SeasonAll.current_season
        season = _detect_active_season(current_season)

    if start_date is None:
        start_date = get_season_start_date(season)

    if end_date is None:
        end_date = date.today()

    # Fetch and cache all NBA team schedules (also returns date->game_ids mapping and game times)
    schedule_refresh.set_progress_display(_progress_display)
    schedule_refresh.set_timing_tracker(_timing_tracker)
    date_game_ids, game_times = schedule_refresh.cache_all_team_schedules(season)

    # Pass progress display and timing tracker to fetcher
    boxscore_fetcher.set_progress_display(_progress_display)
    boxscore_fetcher.set_timing_tracker(_timing_tracker)

    # Start timing boxscore fetch
    if _timing_tracker:
        _timing_tracker.start("boxscore_fetch")

    games_fetched, failed_games = boxscore_fetcher.fetch_and_cache_date_range(
        start_date, end_date, date_game_ids, season, game_times
    )

    # End timing boxscore fetch
    if _timing_tracker:
        _timing_tracker.end("boxscore_fetch")

    # Compute season statistics after fetching games
    if games_fetched > 0:
        if _timing_tracker:
            _timing_tracker.start("stats_computation")

        if _progress_display:
            _progress_display.update_status("Computing season statistics...")

        stats_count = boxscore_cache.compute_and_save_all_season_stats(season)

        if _timing_tracker:
            _timing_tracker.end("stats_computation")

        msg = f"[green]✓[/green] Computed stats for {stats_count} players"
        if _progress_display:
            _progress_display.complete_step(msg)
        else:
            _console.print(msg)

    # Build player-to-team index from boxscore data
    if _timing_tracker:
        _timing_tracker.start("player_indexing")

    if _progress_display:
        _progress_display.update_status("Building player-to-team index...")

    players_indexed = schedule_cache.build_player_team_index_from_boxscores(season)

    if _timing_tracker:
        _timing_tracker.end("player_indexing")

    # Check if indexing was successful
    if players_indexed == 0:
        msg = f"[yellow]⚠[/yellow] Indexed {players_indexed} players to teams (no box scores found?)"
    else:
        msg = f"[green]✓[/green] Indexed {players_indexed} players to teams"

    if _progress_display:
        _progress_display.complete_step(msg)
    else:
        _console.print(msg)

    metadata = boxscore_cache.load_metadata(season)
    players_updated = metadata.get("players_indexed", 0)

    return {
        "games_fetched": games_fetched,
        "games_failed": len(failed_games),
        "players_updated": players_updated,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "season": season,
    }


def initial_build(season_start: Optional[date] = None, season: Optional[str] = None) -> Dict:
    """Build initial cache from scratch for a specific season.

    Clears only the specified season's cache before rebuilding.
    Other seasons' data is preserved.

    Args:
        season_start: Start date (defaults to season start)
        season: Season override (e.g., "2025-26"). If None, auto-detects.

    Returns:
        Summary dictionary
    """
    # Determine season to use first (before clearing)
    if season is None:
        current_season = SeasonAll.current_season
        season = _detect_active_season(current_season)

    # Clear only this season's cache for clean start
    if _progress_display:
        _progress_display.update_status(f"Clearing cache for season {season}...")

    boxscore_cache.clear_season_cache(season)

    if season_start is None:
        season_start = get_season_start_date(season)

    today = date.today()

    # Fetch and cache all NBA team schedules (also returns date->game_ids mapping and game times)
    schedule_refresh.set_progress_display(_progress_display)
    schedule_refresh.set_timing_tracker(_timing_tracker)
    date_game_ids, game_times = schedule_refresh.cache_all_team_schedules(season)

    # Pass progress display and timing tracker to fetcher
    boxscore_fetcher.set_progress_display(_progress_display)
    boxscore_fetcher.set_timing_tracker(_timing_tracker)

    # Start timing boxscore fetch
    if _timing_tracker:
        _timing_tracker.start("boxscore_fetch")

    games_fetched, failed_games = boxscore_fetcher.fetch_and_cache_date_range(
        season_start, today, date_game_ids, season, game_times
    )

    # End timing boxscore fetch
    if _timing_tracker:
        _timing_tracker.end("boxscore_fetch")

    # Build all player indexes
    if _timing_tracker:
        _timing_tracker.start("player_indexing")

    if _progress_display:
        _progress_display.update_status("Building player indexes...")

    players_indexed = boxscore_cache.rebuild_all_player_indexes(season)

    if _timing_tracker:
        _timing_tracker.end("player_indexing")

    msg = f"[green]✓[/green] Indexed {players_indexed} players"
    if _progress_display:
        _progress_display.complete_step(msg)
    else:
        _console.print(msg)

    # Compute season statistics for all players
    if _timing_tracker:
        _timing_tracker.start("stats_computation")

    if _progress_display:
        _progress_display.update_status("Computing season statistics...")

    stats_computed = boxscore_cache.compute_and_save_all_season_stats(season)

    if _timing_tracker:
        _timing_tracker.end("stats_computation")

    msg = f"[green]✓[/green] Computed stats for {stats_computed} players"
    if _progress_display:
        _progress_display.complete_step(msg)
    else:
        _console.print(msg)

    # Build player-to-team index from boxscore data
    if _timing_tracker:
        _timing_tracker.start("team_indexing")

    if _progress_display:
        _progress_display.update_status("Building player-to-team index...")

    players_to_teams = schedule_cache.build_player_team_index_from_boxscores(season)

    if _timing_tracker:
        _timing_tracker.end("team_indexing")

    # Check if indexing was successful
    if players_to_teams == 0:
        msg = f"[yellow]⚠[/yellow] Indexed {players_to_teams} players to teams (no box scores found?)"
    else:
        msg = f"[green]✓[/green] Indexed {players_to_teams} players to teams"

    if _progress_display:
        _progress_display.complete_step(msg)
    else:
        _console.print(msg)

    return {
        "games_fetched": games_fetched,
        "games_failed": len(failed_games),
        "players_updated": players_indexed,
        "start_date": season_start.isoformat(),
        "end_date": today.isoformat(),
        "season": season,
    }


def refresh_players_only(season: Optional[str] = None) -> Dict:
    """Refresh only player indexes from already cached box scores.

    This rebuilds player indexes without making any API calls.
    Useful when box scores are cached but player data needs updating
    (e.g., after code changes to starter logic).

    Args:
        season: Season string (e.g., "2025-26"). If None, auto-detects active season.

    Returns:
        Summary dictionary with players_updated count
    """
    if season is None:
        # Detect active season
        current_season = SeasonAll.current_season
        season = _detect_active_season(current_season)

    # Check if we have cached games for this season
    metadata = boxscore_cache.load_metadata(season)
    games_cached = metadata.get("games_cached", 0)

    if games_cached == 0:
        msg = f"[yellow]⚠[/yellow] No cached games found for season {season}. Run /refresh first to fetch box scores."
        if _progress_display:
            _progress_display.add_line(msg)
        else:
            _console.print(msg)
        return {
            "games_fetched": 0,
            "players_updated": 0,
            "start_date": "",
            "end_date": "",
            "season": season,
        }

    # Rebuild all player indexes from cached games
    if _timing_tracker:
        _timing_tracker.start("player_indexing")

    if _progress_display:
        _progress_display.update_status(
            "Rebuilding player indexes from cached games..."
        )

    players_indexed = boxscore_cache.rebuild_all_player_indexes(season)

    if _timing_tracker:
        _timing_tracker.end("player_indexing")

    msg = f"[green]✓[/green] Rebuilt indexes for {players_indexed} players"
    if _progress_display:
        _progress_display.complete_step(msg)
    else:
        _console.print(msg)

    # Recompute season statistics
    if _timing_tracker:
        _timing_tracker.start("stats_computation")

    if _progress_display:
        _progress_display.update_status("Recomputing season statistics...")

    stats_computed = boxscore_cache.compute_and_save_all_season_stats(season)

    if _timing_tracker:
        _timing_tracker.end("stats_computation")

    msg = f"[green]✓[/green] Recomputed stats for {stats_computed} players"
    if _progress_display:
        _progress_display.complete_step(msg)
    else:
        _console.print(msg)

    # Rebuild player-to-team index
    if _timing_tracker:
        _timing_tracker.start("team_indexing")

    if _progress_display:
        _progress_display.update_status("Rebuilding player-to-team index...")

    players_to_teams = schedule_cache.build_player_team_index_from_boxscores(season)

    if _timing_tracker:
        _timing_tracker.end("team_indexing")

    msg = f"[green]✓[/green] Indexed {players_to_teams} players to teams"
    if _progress_display:
        _progress_display.complete_step(msg)
    else:
        _console.print(msg)

    # Get date range from metadata
    date_range = metadata.get("date_range", {})

    return {
        "games_fetched": 0,
        "players_updated": players_indexed,
        "start_date": date_range.get("start", ""),
        "end_date": date_range.get("end", ""),
        "season": season,
    }


def smart_refresh(season: Optional[str] = None) -> Dict:
    """Smart refresh - only fetch missing dates for a specific season.

    Checks last cached date for the season and fetches from there to today.
    Does NOT rebuild or clear cache when switching seasons - each season
    maintains its own independent cache.

    Args:
        season: Season override (e.g., "2025-26"). If None, auto-detects.

    Returns:
        Summary dictionary
    """
    # Determine season to use
    if season is None:
        current_season = SeasonAll.current_season
        season = _detect_active_season(current_season)

    # Load season-specific metadata
    metadata = boxscore_cache.load_metadata(season)

    # Check if cache exists for this season
    cache_start, cache_end = boxscore_cache.get_cached_date_range(season)

    today = date.today()

    if cache_start is None or cache_end is None:
        # No cache for this season - start fresh from season start
        # This is NOT the same as initial_build (which clears cache)
        # We just fetch data incrementally without clearing anything
        msg = f"[yellow]⚠[/yellow] No cache found for season {season}, fetching from season start..."
        if _progress_display:
            _progress_display.add_line(msg)
        else:
            _console.print(msg)

        # Use refresh_boxscores which does incremental fetch without clearing
        return refresh_boxscores(
            start_date=get_season_start_date(season),
            end_date=today,
            season=season
        )

    # Calculate missing date range
    if cache_end >= today:
        games_cached = metadata.get("games_cached", 0)
        players_indexed = metadata.get("players_indexed", 0)
        msg = f"[green]✓[/green] Cache is up to date for {season} (includes data through {cache_end.isoformat()}, {games_cached} games, {players_indexed} players)"
        if _progress_display:
            _progress_display.add_line(msg)
        else:
            _console.print(msg)
        return {
            "games_fetched": 0,
            "players_updated": players_indexed,
            "start_date": today.isoformat(),
            "end_date": today.isoformat(),
            "season": season,
        }

    # Fetch from cache_end (inclusive) to today
    # This ensures we get complete data for the last cached date in case
    # it was only partially complete (not all games finished) when last fetched
    start_date = cache_end

    # Fetch and cache all NBA team schedules (also returns date->game_ids mapping and game times)
    schedule_refresh.set_progress_display(_progress_display)
    schedule_refresh.set_timing_tracker(_timing_tracker)
    date_game_ids, game_times = schedule_refresh.cache_all_team_schedules(season)

    # Pass progress display and timing tracker to fetcher
    boxscore_fetcher.set_progress_display(_progress_display)
    boxscore_fetcher.set_timing_tracker(_timing_tracker)

    # Start timing boxscore fetch
    if _timing_tracker:
        _timing_tracker.start("boxscore_fetch")

    games_fetched, failed_games = boxscore_fetcher.fetch_and_cache_date_range(
        start_date, today, date_game_ids, season, game_times
    )

    # End timing boxscore fetch
    if _timing_tracker:
        _timing_tracker.end("boxscore_fetch")

    # Update season statistics
    # Always compute if stats don't exist or if new games were added
    stats_dir = boxscore_cache.get_cache_dir() / "season_stats" / season
    if games_fetched > 0 or not stats_dir.exists():
        if _timing_tracker:
            _timing_tracker.start("stats_computation")

        if _progress_display:
            _progress_display.update_status("Computing season statistics...")

        stats_count = boxscore_cache.compute_and_save_all_season_stats(season)

        if _timing_tracker:
            _timing_tracker.end("stats_computation")

        msg = f"[green]✓[/green] Computed stats for {stats_count} players"
        if _progress_display:
            _progress_display.complete_step(msg)
        else:
            _console.print(msg)

    # Build player-to-team index from boxscore data
    if _timing_tracker:
        _timing_tracker.start("player_indexing")

    if _progress_display:
        _progress_display.update_status("Building player-to-team index...")

    players_indexed = schedule_cache.build_player_team_index_from_boxscores(season)

    if _timing_tracker:
        _timing_tracker.end("player_indexing")

    # Check if indexing was successful
    if players_indexed == 0:
        msg = f"[yellow]⚠[/yellow] Indexed {players_indexed} players to teams (no box scores found?)"
    else:
        msg = f"[green]✓[/green] Indexed {players_indexed} players to teams"

    if _progress_display:
        _progress_display.complete_step(msg)
    else:
        _console.print(msg)

    metadata = boxscore_cache.load_metadata(season)
    players_updated = metadata.get("players_indexed", 0)

    return {
        "games_fetched": games_fetched,
        "games_failed": len(failed_games),
        "players_updated": players_updated,
        "start_date": start_date.isoformat(),
        "end_date": today.isoformat(),
        "season": season,
    }
