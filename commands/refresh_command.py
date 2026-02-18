"""Refresh command for updating box score cache."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, List

from commands import Command
from tools.boxscore import boxscore_refresh


class RefreshCommand(Command):
    """Refresh box score cache."""

    @property
    def name(self) -> str:
        return "/refresh"

    @property
    def description(self) -> str:
        return "Refresh box score cache (smart refresh by default - fetches only missing dates; use -s START -e END for specific date range, --today/--yesterday for single day, --force-rebuild to clear cache, -p to rebuild player indexes only)."

    @property
    def arguments(self) -> List[Dict[str, str | bool]]:
        return [
            {
                "name": "-s",
                "required": False,
                "default": "season start (Oct 21)",
                "description": "Start date in YYYY-MM-DD format",
            },
            {
                "name": "-e",
                "required": False,
                "default": "today",
                "description": "End date in YYYY-MM-DD format",
            },
            {
                "name": "--today",
                "required": False,
                "default": "false",
                "description": "Refresh only today's games (shortcut for -s TODAY -e TODAY)",
            },
            {
                "name": "--yesterday",
                "required": False,
                "default": "false",
                "description": "Refresh only yesterday's games (shortcut for -s YESTERDAY -e YESTERDAY)",
            },
            {
                "name": "-p, --players",
                "required": False,
                "default": "false",
                "description": "Rebuild player indexes only (no API calls)",
            },
            {
                "name": "--force-rebuild",
                "required": False,
                "default": "false",
                "description": "Clear cache and rebuild from scratch",
            },
            {
                "name": "-v",
                "required": False,
                "default": "false",
                "description": "Show detailed timing information (verbose mode)",
            },
        ]

    def execute(self, command: str) -> None:
        if self.should_show_help(command):
            self.show_help()
            return
        parts = command.split()

        start_date = None
        end_date = None
        verbose = False
        players_only = False
        today_only = False
        yesterday_only = False
        force_rebuild = False

        # Parse flags
        i = 0
        while i < len(parts):
            part = parts[i]

            if part == "--today":
                today_only = True

            elif part == "--yesterday":
                yesterday_only = True

            elif part == "--force-rebuild":
                force_rebuild = True

            elif part == "-s":
                # Next part should be start date
                if i + 1 < len(parts):
                    try:
                        start_date = date.fromisoformat(parts[i + 1])
                        i += 1
                    except ValueError:
                        self.console.print(
                            f"Invalid date format for -s: {parts[i + 1]}. Use YYYY-MM-DD",
                            style="red",
                        )
                        return
                else:
                    self.console.print(
                        "-s flag requires a date (YYYY-MM-DD)", style="red"
                    )
                    return

            elif part == "-e":
                # Next part should be end date
                if i + 1 < len(parts):
                    try:
                        end_date = date.fromisoformat(parts[i + 1])
                        i += 1
                    except ValueError:
                        self.console.print(
                            f"Invalid date format for -e: {parts[i + 1]}. Use YYYY-MM-DD",
                            style="red",
                        )
                        return
                else:
                    self.console.print(
                        "-e flag requires a date (YYYY-MM-DD)", style="red"
                    )
                    return

            elif part in ("-p", "--players"):
                players_only = True

            elif part in ("-v", "--verbose"):
                verbose = True

            i += 1

        # Apply --today or --yesterday flag (overrides -s and -e)
        if today_only:
            today = date.today()
            start_date = today
            end_date = today
        elif yesterday_only:
            yesterday = date.today() - timedelta(days=1)
            start_date = yesterday
            end_date = yesterday

        # Run refresh with live progress display
        from tools.utils import api_retry
        from tools.utils.progress_display import ProgressDisplay
        from tools.utils.timing import TimingTracker

        # Create timing tracker
        timing_tracker = TimingTracker()

        with ProgressDisplay(self.console) as progress:
            # Set progress display and timing tracker for refresh modules
            boxscore_refresh.set_progress_display(progress)
            boxscore_refresh.set_timing_tracker(timing_tracker)
            api_retry.set_progress_display(progress)

            # Start overall timing
            timing_tracker.start("total_refresh")

            try:
                if players_only:
                    # Players-only mode: rebuild indexes from cached games
                    progress.update_status(
                        "[cyan]Rebuilding player indexes from cached games..."
                    )
                    result = boxscore_refresh.refresh_players_only()
                elif force_rebuild:
                    # Force rebuild: clear cache and rebuild from scratch
                    progress.update_status(
                        "[cyan]Force rebuild: clearing cache and rebuilding from scratch..."
                    )
                    result = boxscore_refresh.initial_build()

                    # Clear waiver cache to force fresh fetch from Yahoo
                    from tools.utils import waiver_cache

                    waiver_cache.clear_all_caches()
                elif (
                    start_date is None
                    and end_date is None
                    and not today_only
                    and not yesterday_only
                ):
                    # Smart refresh: only fetch missing dates (from last cached date to today)
                    progress.update_status(
                        "[cyan]Smart refresh: fetching only missing dates..."
                    )
                    result = boxscore_refresh.smart_refresh()

                    # Clear waiver cache to force fresh fetch from Yahoo
                    from tools.utils import waiver_cache

                    waiver_cache.clear_all_caches()
                else:
                    # Specific date range: fetch requested dates
                    progress.update_status(
                        "[cyan]Refreshing box score cache for specified date range..."
                    )
                    result = boxscore_refresh.refresh_boxscores(start_date, end_date)

                    # Clear waiver cache to force fresh fetch from Yahoo
                    from tools.utils import waiver_cache

                    waiver_cache.clear_all_caches()
            except Exception as err:
                progress.add_line(f"[red]✗[/red] Error refreshing cache: {err}")
                return
            finally:
                # End overall timing
                timing_tracker.end("total_refresh")

            # Display summary
            games_fetched = result.get("games_fetched", 0)
            players_updated = result.get("players_updated", 0)
            start = result.get("start_date", "")
            end = result.get("end_date", "")
            season = result.get("season", "")

            if players_only:
                # Players-only mode: only show player updates
                progress.complete_step(
                    f"[green]✓[/green] Rebuilt indexes for {players_updated} players (Season: {season})"
                )
            else:
                # Full refresh: show games and players
                progress.complete_step(
                    f"[green]✓[/green] Refreshed {games_fetched} games from {start} to {end}"
                )
                progress.complete_step(
                    f"[green]✓[/green] Updated {players_updated} players (Season: {season})"
                )

        # Display timing information only if verbose flag is set
        if verbose:
            self.console.print()
            self.console.print(timing_tracker.format_summary())

            # Show detailed per-date timings if there were multiple dates
            date_timings = [
                t
                for t in timing_tracker.get_detailed_timings()
                if t[0].startswith("fetch_date_")
            ]
            if len(date_timings) > 1:
                self.console.print()
                # Show top 10 slowest dates
                self.console.print("[cyan]Per-date timing (slowest 10):[/cyan]")
                sorted_dates = sorted(date_timings, key=lambda x: x[1], reverse=True)[
                    :10
                ]
                for _, duration, detail in sorted_dates:
                    self.console.print(
                        f"  {detail}: {timing_tracker.format_duration(duration)}"
                    )
