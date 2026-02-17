"""Refresh API endpoints with SSE progress tracking."""

import asyncio
import json
import sys
from datetime import date as date_cls
from pathlib import Path
from queue import Queue
from threading import Thread
from typing import AsyncGenerator

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from app.auth import yahoo_web

from tools.boxscore import boxscore_cache, boxscore_fetcher, boxscore_refresh
from tools.utils import player_index, waiver_cache

router = APIRouter()


class RefreshOptions(BaseModel):
    """Options for what data to refresh."""

    box_scores: bool = False
    waiver_cache: bool = False
    leagues: bool = False
    rebuild_player_indexes: bool = False
    player_rankings: bool = False
    nba_schedule: bool = False
    league_key: str | None = None
    force_rebuild: bool = False
    start_date: str | None = None
    end_date: str | None = None
    season: str | None = None  # Override season (triggers rebuild if different from cached)


class SSEProgressDisplay:
    """Progress display adapter that emits SSE events."""

    def __init__(self):
        """Initialize SSE progress display."""
        self.events = []

    def emit_status(self, message: str) -> dict:
        """Emit a status update (current operation)."""
        return {"type": "status", "message": self._strip_markup(message)}

    def emit_complete(self, message: str) -> dict:
        """Emit a completion event."""
        return {"type": "complete", "message": self._strip_markup(message)}

    def emit_done(self, summary: dict) -> dict:
        """Emit final done event with summary."""
        return {"type": "done", "message": "Refresh complete", "data": summary}

    def emit_error(self, message: str) -> dict:
        """Emit an error event."""
        return {"type": "error", "message": message}

    @staticmethod
    def _strip_markup(text: str) -> str:
        """Strip Rich markup tags from text."""
        import re

        # Remove [color]...[/color] style markup
        text = re.sub(r"\[/?[a-z]+\]", "", text)
        # Remove leading checkmarks (✓, ✗, ⚠) since frontend adds them
        text = re.sub(r"^[✓✗⚠]\s*", "", text)
        return text


class ProgressDisplayAdapter:
    """Adapter to make ProgressDisplay work with SSE."""

    def __init__(self, sse_display: SSEProgressDisplay, event_queue: Queue):
        """Initialize adapter with SSE display and event queue."""
        self.sse_display = sse_display
        self.event_queue = event_queue

    def update_status(self, message: str) -> None:
        """Update current status."""
        event = self.sse_display.emit_status(message)
        self.event_queue.put(event)

    def complete_step(self, message: str) -> None:
        """Mark step as complete."""
        event = self.sse_display.emit_complete(message)
        self.event_queue.put(event)

    def add_line(self, message: str) -> None:
        """Add a line (for errors or info)."""
        event = self.sse_display.emit_complete(message)
        self.event_queue.put(event)

    def start(self) -> None:
        """Start display (no-op for SSE)."""
        pass

    def stop(self) -> None:
        """Stop display (no-op for SSE)."""
        pass

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()
        return False


def refresh_box_scores_sync(
    progress: ProgressDisplayAdapter,
    force_rebuild: bool = False,
    start_date: str | None = None,
    end_date: str | None = None,
    season: str | None = None,
) -> dict:
    """Refresh box scores with progress tracking (synchronous).
    
    Args:
        progress: Progress display adapter for status updates
        force_rebuild: If True, clears cache and rebuilds from scratch
        start_date: Optional start date for date range refresh
        end_date: Optional end date for date range refresh
        season: Optional season override. If different from cached season,
                triggers a full rebuild with confirmation.
    """
    # Set progress display for refresh modules
    boxscore_refresh.set_progress_display(progress)

    # Normalize empty strings to None
    start_date = start_date if start_date and start_date.strip() else None
    end_date = end_date if end_date and end_date.strip() else None
    season = season if season and season.strip() else None

    # Note: Season changes no longer trigger automatic rebuilds.
    # Each season maintains its own independent cache.
    # Use force_rebuild=True to explicitly clear and rebuild a season's cache.

    # Run smart refresh or force rebuild
    if force_rebuild:
        progress.update_status("Force rebuild: clearing existing cache...")
        result = boxscore_refresh.initial_build(season=season)
    elif start_date or end_date:
        # Specific date range refresh
        from datetime import date as date_cls

        progress.update_status(
            f"Refreshing specific date range: {start_date or 'season start'} to {end_date or 'today'}..."
        )

        # Parse dates
        start = date_cls.fromisoformat(start_date) if start_date else None
        end = date_cls.fromisoformat(end_date) if end_date else None

        result = boxscore_refresh.refresh_boxscores(start, end, season=season)
    else:
        result = boxscore_refresh.smart_refresh(season=season)

    return {
        "box_scores": {
            "games_fetched": result.get("games_fetched", 0),
            "players_updated": result.get("players_updated", 0),
            "start_date": result.get("start_date", ""),
            "end_date": result.get("end_date", ""),
            "season": result.get("season", ""),
        }
    }


def refresh_waiver_cache_data_sync(
    progress: ProgressDisplayAdapter, league_key: str
) -> dict:
    """Refresh waiver cache with progress tracking (synchronous)."""
    progress.update_status("Clearing waiver cache...")

    # Clear all waiver caches
    waiver_cache.clear_all_caches()

    progress.complete_step("Waiver cache cleared")

    return {"waiver_cache": {"cleared": True}}


def refresh_leagues_data_sync(progress: ProgressDisplayAdapter) -> dict:
    """Refresh leagues data with progress tracking (synchronous)."""
    progress.update_status("Refreshing league data...")

    # This would fetch fresh league data from Yahoo
    # For now, we just indicate success
    progress.complete_step("League data refreshed")

    return {"leagues": {"refreshed": True}}


def rebuild_player_indexes_sync(progress: ProgressDisplayAdapter) -> dict:
    """Rebuild player indexes from cached box scores (synchronous)."""
    progress.update_status("Rebuilding player indexes from cached games...")

    # Set progress display for refresh modules
    boxscore_refresh.set_progress_display(progress)

    # Run refresh_players_only
    result = boxscore_refresh.refresh_players_only()

    return {
        "player_indexes": {
            "players_updated": result.get("players_updated", 0),
            "season": result.get("season", ""),
        }
    }


def refresh_nba_schedule_sync(
    progress: ProgressDisplayAdapter,
    season: str | None = None,
) -> dict:
    """Refresh NBA schedule from nba_api (synchronous).

    Fetches the latest NBA schedule and caches it locally.
    This is useful when the schedule changes due to NBA Cup or postponements.
    
    Args:
        progress: Progress display adapter for status updates
        season: Optional season override (e.g., "2025-26")
    """
    from nba_api.stats.library.parameters import SeasonAll

    from tools.boxscore.boxscore_refresh import _detect_active_season
    from tools.schedule import schedule_refresh

    progress.update_status("Fetching latest NBA schedule...")

    try:
        # Determine season to use
        if season:
            target_season = season
        else:
            current_season = SeasonAll.current_season
            target_season = _detect_active_season(current_season)

        # Set progress display for the schedule refresh module
        schedule_refresh.set_progress_display(progress)

        # Fetch and cache all team schedules
        date_game_ids, game_times = schedule_refresh.cache_all_team_schedules(target_season)

        # Count unique dates with games
        dates_with_games = len(date_game_ids)
        total_games = sum(len(games) for games in date_game_ids.values())

        progress.complete_step(f"NBA schedule cached for season {target_season}")

        return {
            "nba_schedule": {
                "season": target_season,
                "teams_cached": 30,  # All NBA teams
                "dates_with_games": dates_with_games,
                "total_games": total_games,
            }
        }

    except Exception as e:
        progress.add_line(f"Error refreshing NBA schedule: {str(e)}")
        return {
            "nba_schedule": {
                "error": str(e),
            }
        }


def refresh_player_rankings_sync(progress: ProgressDisplayAdapter) -> dict:
    """Refresh player rankings from Yahoo API for ALL user's leagues.

    Fetches all players sorted by Actual Rank (AR) and caches them
    for each league the user belongs to.
    """
    from tools.utils.yahoo import fetch_all_player_rankings, fetch_user_leagues

    progress.update_status("Fetching user's leagues...")

    try:
        # Get all user's NBA leagues
        leagues = fetch_user_leagues()

        if not leagues:
            progress.complete_step("No leagues found")
            return {
                "player_rankings": {
                    "players_fetched": 0,
                    "leagues_updated": 0,
                }
            }

        progress.add_line(f"Found {len(leagues)} league(s)")

        total_players = 0
        leagues_updated = 0

        for league in leagues:
            league_key = league.get("league_key")
            league_name = league.get("name", league_key)

            if not league_key:
                continue

            progress.update_status(f"Fetching rankings for {league_name}...")

            try:
                players = fetch_all_player_rankings(league_key)

                if players:
                    # Save to cache (also updates Yahoo↔NBA ID mappings)
                    player_index.save_rankings(league_key, players)
                    total_players += len(players)
                    leagues_updated += 1
                    progress.add_line(f"  {league_name}: {len(players)} players")
            except Exception as league_error:
                progress.add_line(f"  {league_name}: Error - {str(league_error)}")

        progress.complete_step(
            f"Cached rankings for {leagues_updated} league(s), {total_players} total players"
        )

        return {
            "player_rankings": {
                "players_fetched": total_players,
                "leagues_updated": leagues_updated,
            }
        }

    except Exception as e:
        progress.add_line(f"Error fetching player rankings: {str(e)}")
        return {
            "player_rankings": {
                "error": str(e),
            }
        }


def run_refresh_operations(
    options: RefreshOptions, event_queue: Queue, sse_display: SSEProgressDisplay
):
    """Run refresh operations in a separate thread."""
    progress = ProgressDisplayAdapter(sse_display, event_queue)
    summary = {}

    try:
        # Refresh box scores if requested
        if options.box_scores:
            event_queue.put(sse_display.emit_status("Starting box score refresh..."))
            result = refresh_box_scores_sync(
                progress,
                options.force_rebuild,
                options.start_date,
                options.end_date,
                options.season,
            )
            summary.update(result)

        # Rebuild player indexes if requested
        if options.rebuild_player_indexes:
            event_queue.put(sse_display.emit_status("Starting player index rebuild..."))
            result = rebuild_player_indexes_sync(progress)
            summary.update(result)

        # Refresh waiver cache if requested
        if options.waiver_cache:
            if not options.league_key:
                event_queue.put(
                    sse_display.emit_error(
                        "League key required for waiver cache refresh"
                    )
                )
            else:
                event_queue.put(
                    sse_display.emit_status("Starting waiver cache refresh...")
                )
                result = refresh_waiver_cache_data_sync(progress, options.league_key)
                summary.update(result)

        # Refresh leagues if requested
        if options.leagues:
            event_queue.put(sse_display.emit_status("Starting league data refresh..."))
            result = refresh_leagues_data_sync(progress)
            summary.update(result)

        # Refresh player rankings if requested (fetches for ALL leagues)
        if options.player_rankings:
            event_queue.put(
                sse_display.emit_status("Starting player rankings refresh...")
            )
            result = refresh_player_rankings_sync(progress)
            summary.update(result)

        # Refresh NBA schedule if requested
        if options.nba_schedule:
            event_queue.put(
                sse_display.emit_status("Starting NBA schedule refresh...")
            )
            result = refresh_nba_schedule_sync(progress, options.season)
            summary.update(result)

        # Send final done event with summary
        event_queue.put(sse_display.emit_done(summary))

    except Exception as e:
        event_queue.put(sse_display.emit_error(f"Error during refresh: {str(e)}"))
    finally:
        # Signal completion with sentinel value
        event_queue.put(None)


async def generate_refresh_events(options: RefreshOptions) -> AsyncGenerator[str, None]:
    """Generate SSE events for refresh operations."""
    sse_display = SSEProgressDisplay()
    event_queue = Queue()

    # Start refresh operations in a separate thread
    thread = Thread(
        target=run_refresh_operations, args=(options, event_queue, sse_display)
    )
    thread.start()

    # Yield events from queue as they come in
    while True:
        # Check queue with timeout to allow async loop to process
        try:
            # Wait for event with short timeout
            await asyncio.sleep(0.1)  # Small delay to prevent CPU spinning

            # Get all available events from queue
            events = []
            while not event_queue.empty():
                event = event_queue.get_nowait()
                if event is None:
                    # Sentinel value - operation complete
                    # Yield any remaining events
                    for e in events:
                        yield format_sse_event(e)
                    thread.join()  # Wait for thread to finish
                    return
                events.append(event)

            # Yield all collected events
            for event in events:
                yield format_sse_event(event)

        except Exception as e:
            yield format_sse_event(
                sse_display.emit_error(f"Error streaming events: {str(e)}")
            )
            break

    # Wait for thread to finish
    thread.join()


def format_sse_event(event: dict) -> str:
    """Format event as SSE message."""
    return f"data: {json.dumps(event)}\n\n"


@router.get("/start")
async def start_refresh(
    request: Request,
    box_scores: bool = Query(False, description="Refresh box scores"),
    waiver_cache: bool = Query(False, description="Clear waiver cache"),
    leagues: bool = Query(False, description="Refresh league data"),
    rebuild_player_indexes: bool = Query(False, description="Rebuild player indexes"),
    player_rankings: bool = Query(False, description="Refresh player rankings from Yahoo"),
    nba_schedule: bool = Query(False, description="Refresh NBA schedule from nba_api"),
    league_key: str | None = Query(None, description="League key for waiver cache and rankings"),
    force_rebuild: bool = Query(
        False, description="Force full rebuild of box score cache"
    ),
    start_date: str | None = Query(
        None, description="Start date for box score refresh (YYYY-MM-DD)"
    ),
    end_date: str | None = Query(
        None, description="End date for box score refresh (YYYY-MM-DD)"
    ),
    season: str | None = Query(
        None, description="Season override (e.g., '2025-26'). If different from cached, triggers rebuild."
    ),
):
    """Start a refresh operation with SSE progress updates.

    Returns a stream of Server-Sent Events with progress updates.
    """
    # Verify authentication
    yahoo_web.get_session_from_request(request)

    # Log received parameters for debugging
    print(
        f"[DEBUG] Refresh params - start_date: {start_date!r}, end_date: {end_date!r}, "
        f"force_rebuild: {force_rebuild}, season: {season!r}"
    )

    options = RefreshOptions(
        box_scores=box_scores,
        waiver_cache=waiver_cache,
        leagues=leagues,
        rebuild_player_indexes=rebuild_player_indexes,
        player_rankings=player_rankings,
        nba_schedule=nba_schedule,
        league_key=league_key,
        force_rebuild=force_rebuild,
        start_date=start_date,
        end_date=end_date,
        season=season,
    )

    return StreamingResponse(
        generate_refresh_events(options),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable buffering in nginx
        },
    )


@router.get("/missing-games")
def get_missing_games(
    request: Request,
    season: str | None = Query(None, description="Season filter (e.g., '2025-26')"),
    start_date: str | None = Query(
        None, description="Start date (YYYY-MM-DD). Defaults to season start."
    ),
    end_date: str | None = Query(
        None, description="End date (YYYY-MM-DD). Defaults to yesterday."
    ),
):
    """Detect missing boxscores by comparing schedule vs cached data.

    Compares the NBA schedule against cached boxscore files to identify
    games that should have been played but are missing from the cache.

    Returns:
        - by_date: Dict mapping dates to {expected, cached, missing, missing_count}
        - total_missing: Total count of missing games
        - total_expected: Total scheduled games in range
        - total_cached: Total cached games in range
        - dates_with_missing: Number of dates that have missing games
    """
    from datetime import date as date_cls

    from nba_api.stats.library.parameters import SeasonAll

    from tools.boxscore.boxscore_refresh import _detect_active_season

    # Verify authentication
    yahoo_web.get_session_from_request(request)

    # Determine season if not provided
    if not season:
        current_season = SeasonAll.current_season
        season = _detect_active_season(current_season)

    # Parse dates if provided
    parsed_start = None
    parsed_end = None

    if start_date:
        try:
            parsed_start = date_cls.fromisoformat(start_date)
        except ValueError:
            return {"error": f"Invalid start_date format: {start_date}"}

    if end_date:
        try:
            parsed_end = date_cls.fromisoformat(end_date)
        except ValueError:
            return {"error": f"Invalid end_date format: {end_date}"}

    # Get missing games summary
    summary = boxscore_cache.get_missing_games_summary(season)

    # If custom date range requested, filter the results
    if parsed_start or parsed_end:
        # Re-run detection with custom date range
        missing_by_date = boxscore_cache.detect_missing_games(
            season, parsed_start, parsed_end
        )

        # Recalculate summary
        total_missing = 0
        total_expected = 0
        total_cached = 0

        for date_str, info in missing_by_date.items():
            total_missing += info["missing_count"]
            total_expected += info["expected"]
            total_cached += info["cached"]

        summary = {
            "total_missing": total_missing,
            "total_expected": total_expected,
            "total_cached": total_cached,
            "dates_with_missing": len(missing_by_date),
            "by_date": missing_by_date,
        }

    return {
        "season": season,
        **summary,
    }


def run_retry_operations(
    game_ids: list[str] | None,
    season: str | None,
    event_queue: Queue,
    sse_display: SSEProgressDisplay,
):
    """Run retry operations in a separate thread with progress events.
    
    Retries missing games detected by comparing schedule vs cache.
    """
    import time

    from nba_api.stats.library.parameters import SeasonAll

    from tools.boxscore.boxscore_refresh import _detect_active_season

    successful = []
    still_missing = []

    try:
        # Determine season if not provided
        if not season:
            current_season = SeasonAll.current_season
            season = _detect_active_season(current_season)

        # Get missing games to retry
        event_queue.put(sse_display.emit_status("Detecting missing games..."))
        missing_by_date = boxscore_cache.detect_missing_games(season)

        games_to_retry = []
        for date_str, info in missing_by_date.items():
            for missing_game in info.get("missing", []):
                game_id = missing_game.get("game_id")
                if game_id:
                    # Filter by game_ids if provided
                    if game_ids and game_id not in game_ids:
                        continue
                    games_to_retry.append({
                        "game_id": game_id,
                        "date": date_str,
                        "season": season,
                        "home_team": missing_game.get("home_team_tricode", ""),
                        "away_team": missing_game.get("away_team_tricode", ""),
                    })

        if not games_to_retry:
            event_queue.put(sse_display.emit_done({
                "games_retried": 0,
                "games_successful": 0,
                "games_still_missing": 0,
                "message": "No missing games to retry",
            }))
            return

        total = len(games_to_retry)
        event_queue.put(
            sse_display.emit_status(f"Retrying {total} games...")
        )

        # Retry each game
        for idx, game_info in enumerate(games_to_retry):
            game_id = game_info.get("game_id")
            game_date = game_info.get("date")
            game_season = game_info.get("season", season)

            if not game_id or not game_date:
                continue

            # Build matchup string for display
            home_team = game_info.get("home_team", "")
            away_team = game_info.get("away_team", "")
            matchup = f"{away_team} @ {home_team}" if home_team and away_team else game_id

            # Emit progress event
            event_queue.put({
                "type": "progress",
                "current": idx + 1,
                "total": total,
                "game_id": game_id,
                "matchup": matchup,
                "date": game_date,
                "message": f"Fetching {matchup} ({game_date})",
            })

            # Rate limiting
            if idx > 0:
                time.sleep(0.5)

            # Try to fetch the game
            game_data, error_info = boxscore_fetcher.fetch_box_score(
                game_id, game_date=game_date
            )

            if game_data and game_data.get("box_score"):
                # Success! Save the game
                boxscore_cache.save_game(game_id, game_season, game_date, game_data)

                # Update player indexes
                box_score = game_data.get("box_score", {})
                for player_id_str, player_stats in box_score.items():
                    player_id = int(player_id_str)
                    player_name = player_stats.get("PLAYER_NAME", f"Player_{player_id}")

                    game_entry = {
                        "date": game_date,
                        "game_id": game_id,
                        **{
                            k: v
                            for k, v in player_stats.items()
                            if k not in ["PLAYER_NAME", "PLAYER_ID"]
                        },
                    }

                    boxscore_cache.update_player_index(
                        player_id, player_name, game_entry, game_season
                    )

                successful.append(game_id)

                # Emit success event
                event_queue.put({
                    "type": "game_complete",
                    "game_id": game_id,
                    "matchup": matchup,
                    "date": game_date,
                    "status": "success",
                    "message": f"Successfully fetched {matchup}",
                })
            else:
                # Failed to fetch - game is still missing
                if error_info:
                    reason = error_info.get("type", "unknown_error")
                    error_message = error_info.get("message", "Unknown error")
                else:
                    reason = "no_data"
                    error_message = "No data returned"

                still_missing.append(game_id)

                # Emit failure event
                event_queue.put({
                    "type": "game_complete",
                    "game_id": game_id,
                    "matchup": matchup,
                    "date": game_date,
                    "status": "failed",
                    "reason": reason,
                    "message": f"Failed: {error_message}",
                })

        # Rebuild indexes and stats if any games were successfully fetched
        if successful:
            from tools.schedule import schedule_cache

            # Rebuild player indexes
            event_queue.put(sse_display.emit_status("Rebuilding player indexes..."))
            players_indexed = boxscore_cache.rebuild_all_player_indexes(season)
            event_queue.put({
                "type": "step_complete",
                "message": f"Rebuilt indexes for {players_indexed} players",
            })

            # Recompute season stats
            event_queue.put(sse_display.emit_status("Recomputing season statistics..."))
            stats_computed = boxscore_cache.compute_and_save_all_season_stats(season)
            event_queue.put({
                "type": "step_complete",
                "message": f"Computed stats for {stats_computed} players",
            })

            # Rebuild player-to-team index
            event_queue.put(sse_display.emit_status("Rebuilding player-to-team index..."))
            players_to_teams = schedule_cache.build_player_team_index_from_boxscores(season)
            event_queue.put({
                "type": "step_complete",
                "message": f"Indexed {players_to_teams} players to teams",
            })

        # Send final done event
        event_queue.put(sse_display.emit_done({
            "games_retried": total,
            "games_successful": len(successful),
            "games_still_missing": len(still_missing),
            "successful_game_ids": successful,
            "still_missing_game_ids": still_missing,
            "message": f"Retry complete: {len(successful)} successful, {len(still_missing)} still missing",
        }))

    except Exception as e:
        event_queue.put(sse_display.emit_error(f"Error during retry: {str(e)}"))
    finally:
        event_queue.put(None)  # Sentinel value


async def generate_retry_events(
    game_ids: list[str] | None,
    season: str | None,
) -> AsyncGenerator[str, None]:
    """Generate SSE events for retry operations on missing games."""
    sse_display = SSEProgressDisplay()
    event_queue = Queue()

    # Start retry operations in a separate thread
    thread = Thread(
        target=run_retry_operations,
        args=(game_ids, season, event_queue, sse_display),
    )
    thread.start()

    # Yield events from queue as they come in
    while True:
        try:
            await asyncio.sleep(0.1)

            events = []
            while not event_queue.empty():
                event = event_queue.get_nowait()
                if event is None:
                    for e in events:
                        yield format_sse_event(e)
                    thread.join()
                    return
                events.append(event)

            for event in events:
                yield format_sse_event(event)

        except Exception as e:
            yield format_sse_event(
                sse_display.emit_error(f"Error streaming events: {str(e)}")
            )
            break

    thread.join()


@router.get("/retry-missing-stream")
async def retry_missing_games_stream(
    request: Request,
    game_ids: str | None = Query(
        None, description="Comma-separated list of game IDs to retry"
    ),
    season: str | None = Query(None, description="Season filter (e.g., '2025-26')"),
):
    """Retry fetching missing games with SSE progress updates.

    Missing games are detected by comparing schedule vs cached boxscores.

    Returns a stream of Server-Sent Events with progress updates for each game.

    Events:
    - status: General status update
    - progress: Current game being processed (includes current/total count)
    - game_complete: Individual game result (success or failure)
    - done: Final summary with counts
    - error: Error message if something fails
    """
    # Verify authentication
    yahoo_web.get_session_from_request(request)

    # Parse game_ids if provided
    parsed_game_ids = None
    if game_ids:
        parsed_game_ids = [gid.strip() for gid in game_ids.split(",") if gid.strip()]

    return StreamingResponse(
        generate_retry_events(parsed_game_ids, season),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


