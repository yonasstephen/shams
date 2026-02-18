"""Waiver wire command for the Shams CLI."""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from rich.console import Console
from rich.table import Table

from commands import Command
from commands.league_context import LeagueContext
from tools.player.player_fetcher import clear_game_log_caches
from tools.player.player_minutes_trend import (
    NBA_API_TIMEOUT,
    TrendComputation,
    process_minute_trend_query,
)
from tools.schedule.schedule_fetcher import get_season_start_date
from tools.utils.render import _get_stat_color


def render_waiver_table(
    players: Sequence[dict], stats_mode: str = "last", agg_mode: str = "avg"
) -> Table:
    # Format the title with mode information
    # Parse stats_mode to create readable label
    mode_lower = stats_mode.lower()
    if mode_lower == "last":
        period_label = "Last Game"
    elif mode_lower == "season":
        period_label = "Season"
    elif mode_lower.startswith("last"):
        # Extract number from 'last7', 'last10', 'last7d', etc.
        try:
            if mode_lower.endswith("d"):
                # Date-based (e.g., 'last7d')
                num = mode_lower[4:-1]
                period_label = f"Last {num} Days"
            else:
                # Game-based (e.g., 'last7')
                num = mode_lower[4:]
                period_label = f"Last {num} Games"
        except (ValueError, IndexError):
            period_label = "Last Game"
    else:
        period_label = "Last Game"

    # Capitalize aggregation mode
    agg_label = "Avg" if agg_mode == "avg" else "Sum"

    title = f"Top Waiver Wire Players ({period_label} - {agg_label})"
    table = Table(title=title)
    table.add_column("#", justify="center", style="dim")
    table.add_column("Player", justify="left")
    table.add_column("Status", justify="center")
    table.add_column("Injury", justify="left", style="dim")
    table.add_column("Last Game", justify="center", style="dim")
    table.add_column("Games", justify="center")

    # Minute-related columns
    table.add_column("Min Trend", justify="right")
    table.add_column("Minute", justify="right")

    # 9-category stats columns
    table.add_column("FG%", justify="right")
    table.add_column("FT%", justify="right")
    table.add_column("3PM", justify="right")
    table.add_column("PTS", justify="right")
    table.add_column("REB", justify="right")
    table.add_column("AST", justify="right")
    table.add_column("STL", justify="right")
    table.add_column("BLK", justify="right")
    table.add_column("TO", justify="right")
    table.add_column("+/-", justify="right")
    table.add_column("USG%", justify="right")
    table.add_column("Starter", justify="center")

    for idx, player in enumerate(players, start=1):
        trend_value = player["trend"]
        trend_color = (
            "green" if trend_value > 0 else "red" if trend_value < 0 else "grey37"
        )
        status = player.get("status", "FA")
        injury_status = player.get("injury_status", "")
        injury_note = player.get("injury_note", "")
        stats = player.get("stats")
        minutes = player.get("minutes", 0.0)
        last_game_date = player.get("last_game_date", "")
        remaining_games = player.get("remaining_games", 0)
        total_games = player.get("total_games", 0)

        # Color code status: W = yellow, FA = green
        status_color = "yellow" if status == "W" else "green"

        # Format injury information with color coding
        injury_display = ""
        if injury_status:
            # Normalize injury status for consistent display
            injury_upper = injury_status.upper()

            # Color code based on severity
            if injury_upper in ("INJ", "O", "OUT"):
                injury_color = "red"
                injury_display = f"[{injury_color}]{injury_upper}[/{injury_color}]"
            elif injury_upper in ("DTD", "QUES", "Q"):
                injury_color = "yellow"
                injury_display = f"[{injury_color}]{injury_upper}[/{injury_color}]"
            elif injury_upper in ("IR", "SUSP", "PUP", "NA"):
                injury_color = "red"
                injury_display = f"[{injury_color}]{injury_upper}[/{injury_color}]"
            else:
                # Unknown status, show as-is
                injury_display = injury_upper

            # Add injury note if available (truncate if too long)
            if injury_note:
                note_truncated = (
                    injury_note[:30] + "..." if len(injury_note) > 30 else injury_note
                )
                injury_display += f" {note_truncated}"

        # Color code minutes
        minute_color = _get_stat_color("Minute", minutes)

        # Format stats or show N/A if not available
        if stats:
            # Format FG% and FT% with makes/attempts and color coding
            if stats.fga > 0:
                fg_color = _get_stat_color("FG%", stats.fg_pct)
                fg_pct = f"[{fg_color}]{stats.fg_pct:.1%}[/{fg_color}] ({stats.fgm:.0f}/{stats.fga:.0f})"
            else:
                fg_pct = "-"

            if stats.fta > 0:
                ft_color = _get_stat_color("FT%", stats.ft_pct)
                ft_pct = f"[{ft_color}]{stats.ft_pct:.1%}[/{ft_color}] ({stats.ftm:.0f}/{stats.fta:.0f})"
            else:
                ft_pct = "-"

            # Apply color coding to counting stats
            threes_color = _get_stat_color("3PM", stats.threes)
            points_color = _get_stat_color("PTS", stats.points)
            rebounds_color = _get_stat_color("REB", stats.rebounds)
            assists_color = _get_stat_color("AST", stats.assists)
            steals_color = _get_stat_color("STL", stats.steals)
            blocks_color = _get_stat_color("BLK", stats.blocks)
            turnovers_color = _get_stat_color("TO", stats.turnovers)
            plus_minus_color = _get_stat_color("+/-", stats.plus_minus)
            usage_color = _get_stat_color("USG%", stats.usage_pct)

            threes = f"[{threes_color}]{stats.threes:.1f}[/{threes_color}]"
            points = f"[{points_color}]{stats.points:.1f}[/{points_color}]"
            rebounds = f"[{rebounds_color}]{stats.rebounds:.1f}[/{rebounds_color}]"
            assists = f"[{assists_color}]{stats.assists:.1f}[/{assists_color}]"
            steals = f"[{steals_color}]{stats.steals:.1f}[/{steals_color}]"
            blocks = f"[{blocks_color}]{stats.blocks:.1f}[/{blocks_color}]"
            turnovers = f"[{turnovers_color}]{stats.turnovers:.1f}[/{turnovers_color}]"
            plus_minus = (
                f"[{plus_minus_color}]{stats.plus_minus:+.1f}[/{plus_minus_color}]"
            )
            usage = f"[{usage_color}]{stats.usage_pct:.1%}[/{usage_color}]"

            # Format starter column: N/M with color coding
            # Green for 100%, yellow for 50%+, gray for <50%
            games_started = stats.games_started
            games_count = stats.games_count

            if games_count > 0:
                start_pct = games_started / games_count
                if start_pct == 1.0:
                    starter_color = "green"
                elif start_pct >= 0.5:
                    starter_color = "yellow"
                else:
                    starter_color = "grey37"
                starter = (
                    f"[{starter_color}]{games_started}/{games_count}[/{starter_color}]"
                )
            else:
                starter = "0/0"
        else:
            fg_pct = ft_pct = threes = points = rebounds = assists = steals = blocks = (
                turnovers
            ) = plus_minus = usage = starter = "N/A"

        # Format last game date
        last_game_display = last_game_date if last_game_date else "-"

        # Format games with color coding (same as matchup)
        if remaining_games == 0:
            games_color = "dim"  # Dark gray for zero games remaining
        elif remaining_games >= 4:
            games_color = "green"
        elif remaining_games > 2:
            games_color = "yellow"
        else:
            games_color = "red"
        games_display = (
            f"[{games_color}]({remaining_games}/{total_games})[/{games_color}]"
        )

        table.add_row(
            str(idx),
            player["name"],
            f"[{status_color}]{status}[/{status_color}]",
            injury_display if injury_display else "-",
            last_game_display,
            games_display,
            f"[{trend_color}]{trend_value:+.1f}[/{trend_color}]",
            f"[{minute_color}]{minutes:.1f}m[/{minute_color}]",
            fg_pct,
            ft_pct,
            threes,
            points,
            rebounds,
            assists,
            steals,
            blocks,
            turnovers,
            plus_minus,
            usage,
            starter,
        )

    return table


class WaiverCommand(Command):
    """List top waiver players sorted by minute trend."""

    def __init__(self, console: Console, league_context: LeagueContext) -> None:
        super().__init__(console)
        self.league_context = league_context

    @property
    def name(self) -> str:
        return "/waiver"

    @property
    def description(self) -> str:
        return "List top waiver players sorted by minute trend."

    @property
    def arguments(self) -> List[Dict[str, str | bool]]:
        return [
            {
                "name": "[league_key]",
                "required": False,
                "default": "default league",
                "description": "Yahoo league key",
            },
            {
                "name": "-r",
                "required": False,
                "description": "Refresh player cache from Yahoo API",
            },
            {
                "name": "-n",
                "required": False,
                "default": "50",
                "description": "Number of players to display (e.g., -n 20)",
            },
            {
                "name": "-l, --lookback",
                "required": False,
                "default": "last",
                "description": "Lookback period: 'last' (last game), 'lastN' (last N games), 'lastNd' (last N days), 'season'",
            },
            {
                "name": "-a, --agg",
                "required": False,
                "default": "avg",
                "description": "Aggregation method: 'avg' (average) or 'sum'",
            },
            {
                "name": "-o, --sort, --orderby",
                "required": False,
                "default": "Yahoo ranking",
                "description": "Column to sort by (case-insensitive) [FG%|FT%|3PM|PTS|REB|AST|STL|BLK|TO|+/-|USG%|STARTER|TREND|MIN]",
            },
            {
                "name": "--asc",
                "required": False,
                "description": "Sort in ascending order (use with -o/--sort/--orderby)",
            },
            {
                "name": "--desc",
                "required": False,
                "description": "Sort in descending order (use with -o/--sort/--orderby)",
            },
        ]

    def execute(self, command: str) -> None:  # pylint: disable=too-many-return-statements
        if self.should_show_help(command):
            self.show_help()
            return
        parts = command.split()

        # Parse arguments
        refresh_cache = False
        display_count = 50  # Default to 50 players
        stats_mode = "last"  # Default to last game stats
        agg_mode = "avg"  # Default to average aggregation
        sort_column = None
        sort_ascending = None  # None means use smart defaults

        # Filter out flags and extract league key
        filtered_parts = []
        i = 0
        while i < len(parts):
            part = parts[i]
            if part == "-r":
                refresh_cache = True
            elif part == "-n":
                # Next part should be the count
                if i + 1 < len(parts):
                    try:
                        display_count = int(parts[i + 1])
                        i += 1  # Skip the count value
                    except ValueError:
                        self.console.print(
                            "Invalid count value for -n flag", style="red"
                        )
                        return
                else:
                    self.console.print("-n flag requires a count value", style="red")
                    return
            elif part in ("-l", "--lookback"):
                # Next part should be the stats mode
                if i + 1 < len(parts):
                    stats_mode = parts[i + 1]
                    i += 1  # Skip the mode value
                else:
                    self.console.print(
                        "-l/--lookback flag requires a mode value", style="red"
                    )
                    return
            elif part in ("-a", "--agg"):
                # Next part should be the aggregation mode
                if i + 1 < len(parts):
                    agg_mode = parts[i + 1].lower()
                    if agg_mode not in ("avg", "sum"):
                        self.console.print(
                            "Aggregation mode must be 'avg' or 'sum'", style="red"
                        )
                        return
                    i += 1  # Skip the mode value
                else:
                    self.console.print(
                        "-a/--agg flag requires a mode value", style="red"
                    )
                    return
            elif part in ("-o", "--sort", "--orderby"):
                # Next part should be the sort column
                if i + 1 < len(parts):
                    sort_column = parts[i + 1]
                    i += 1  # Skip the column value
                else:
                    self.console.print(
                        f"{part} flag requires a column value", style="red"
                    )
                    return
            elif part == "--asc":
                sort_ascending = True
            elif part == "--desc":
                sort_ascending = False
            else:
                filtered_parts.append(part)
            i += 1

        league_key = self.league_context.resolve_league_key(filtered_parts)
        if not league_key:
            return

        if len(filtered_parts) <= 1:
            self.console.print(f"Using default league {league_key}.", style="cyan")

        # Clear caches to get fresh game log data
        clear_game_log_caches()

        from tools.utils.progress_display import ProgressDisplay

        with ProgressDisplay(self.console) as progress:
            try:
                trends = self._compute_waiver_trends(
                    league_key,
                    refresh_cache=refresh_cache,
                    display_count=display_count,
                    stats_mode=stats_mode,
                    agg_mode=agg_mode,
                    sort_column=sort_column,
                    sort_ascending=sort_ascending,
                    progress=progress,
                )
            except Exception as err:  # noqa: BLE001
                self.console.print(f"Error fetching waiver data: {err}", style="red")
                return

        if not trends:
            self.console.print(
                "No waiver players with recent games found.", style="yellow"
            )
            return

        self.console.print(
            render_waiver_table(trends, stats_mode=stats_mode, agg_mode=agg_mode)
        )

    def _compute_waiver_trends(
        self,
        league_key: str,
        refresh_cache: bool = False,
        display_count: int = 50,
        stats_mode: str = "last",
        agg_mode: str = "avg",
        sort_column: Optional[str] = None,
        sort_ascending: Optional[bool] = None,
        progress=None,
    ) -> Sequence[dict]:
        """Compute minute trends and 9-cat stats for waiver wire players.

        Args:
            league_key: The Yahoo league key
            refresh_cache: If True, fetch all players from API and refresh cache
            display_count: Number of top players to return
            stats_mode: Stats calculation mode ('last', 'lastN', or 'season')
            agg_mode: Aggregation mode ('avg' for average, 'sum' for total)
            sort_column: Optional column to sort by (default: Yahoo ranking)
            sort_ascending: If True, sort ascending; if False, sort descending;
                          if None, use smart defaults

        Returns:
            List of player dictionaries with trend and stats data
        """
        from datetime import date as date_cls

        # Check if box score cache needs refresh
        from tools.boxscore import boxscore_cache, boxscore_refresh
        from tools.schedule import schedule_fetcher
        from tools.utils import waiver_cache
        from tools.utils.yahoo import (
            determine_current_week,
            extract_team_id,
            fetch_free_agents_and_waivers,
            fetch_matchup_context,
            fetch_user_team_key,
        )

        metadata = boxscore_cache.load_metadata()
        games_cached = metadata.get("games_cached", 0)
        cache_end_date = metadata.get("date_range", {}).get("end")

        # Auto-refresh if cache is stale (not updated today)
        needs_refresh = False
        if games_cached == 0:
            needs_refresh = True
            self.console.print(
                "[yellow]No game data in cache. Building cache...[/yellow]"
            )
        elif cache_end_date and cache_end_date != date_cls.today().isoformat():
            needs_refresh = True
            self.console.print(
                f"[yellow]Cache outdated (last: {cache_end_date}). Refreshing...[/yellow]"
            )

        if needs_refresh:
            with self.console.status(
                "[cyan]Refreshing box score cache...", spinner="dots"
            ):
                result = boxscore_refresh.smart_refresh()

            games_added = result.get("games_fetched", 0)
            if games_added > 0:
                self.console.print(
                    f"[green]✓[/green] Updated cache: {games_added} new games\n"
                )
            else:
                self.console.print("[dim]Cache is up to date (no new games)[/dim]\n")

        # Get current week date range for games calculation
        week_start = None
        week_end = None
        try:
            team_key = fetch_user_team_key(league_key)
            team_id = extract_team_id(team_key)
            current_week = determine_current_week(league_key, team_id)
            matchup, _ = fetch_matchup_context(league_key, team_key, week=current_week)
            week_start = date_cls.fromisoformat(matchup.week_start)
            week_end = date_cls.fromisoformat(matchup.week_end)
        except Exception:
            # If we can't get week info, we'll skip games calculation
            pass

        # Try to load from cache first
        players = None
        if not refresh_cache:
            if progress:
                progress.update_status("[cyan]Loading cached waiver players...")
            players = waiver_cache.load_cached_players(league_key)
            if progress and players:
                progress.complete_step(
                    f"[green]✓[/green] Loaded {len(players)} players from cache"
                )

        # If no cache or refresh requested, fetch all players
        # Uses WAIVER_BATCH_SIZE from environment (default: 50)
        if players is None:
            if progress:
                progress.update_status("[cyan]Fetching waiver players from Yahoo...")
            players = fetch_free_agents_and_waivers(league_key)
            if progress:
                progress.complete_step(
                    f"[green]✓[/green] Fetched {len(players)} waiver players"
                )
            # Save to cache for future use
            waiver_cache.save_cached_players(league_key, players)

        enriched = []

        # Process all available players (no limit needed since everything is cached)
        if progress:
            progress.update_status(f"[cyan]Processing {len(players)} players...")

        processed_count = 0
        skipped_count = 0

        for idx, player in enumerate(players, 1):
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

            # Update progress every 10 players
            if progress and idx % 10 == 0:
                progress.update_status(
                    f"[cyan]Processing players... "
                    f"({processed_count} with NBA data, {skipped_count} without)[/cyan]"
                )

            try:
                # process_minute_trend_query will use cache first, then fall back to API if needed
                # Since we auto-refreshed cache above, most players should be cached
                result = process_minute_trend_query(
                    name,
                    "Regular Season",
                    suggestion_limit=5,
                    timeout=NBA_API_TIMEOUT,
                )
            except (ValueError, Exception):
                # Skip players we can't fetch data for
                # (e.g., not found, no games, timeout)
                skipped_count += 1
                continue

            if isinstance(result, TrendComputation):
                # Compute 9-cat stats for this player
                from tools.player.player_minutes_trend import find_player_matches
                from tools.player.player_stats import (
                    _parse_stat_mode,
                    compute_player_stats,
                )

                player_stats = None
                player_id, _ = find_player_matches(name, limit=1)
                if player_id:
                    season_start = get_season_start_date("2025-26")
                    today = date_cls.today()
                    player_stats = compute_player_stats(
                        player_id, stats_mode, season_start, today, agg_mode
                    )

                # Calculate average minutes based on stats mode
                num_games, num_days = _parse_stat_mode(stats_mode)
                if num_games == 1:
                    # Show last game minutes
                    avg_minutes = result.last_minutes
                elif num_days is not None:
                    # For date-based filtering, calculate average from available games
                    # Filter logs by date
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
                    # Calculate average over the requested games
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
                if week_start and week_end and player_id:
                    try:
                        schedule = (
                            schedule_fetcher.fetch_player_upcoming_games_from_cache(
                                player_id,
                                week_start.isoformat(),
                                week_end.isoformat(),
                                "2025-26",
                            )
                        )
                        total_games = (
                            len(schedule.game_dates) if schedule.game_dates else 0
                        )
                        # Calculate remaining games (from today onwards)
                        today = date_cls.today()
                        remaining_dates = [
                            d for d in schedule.game_dates if d >= today.isoformat()
                        ]
                        remaining_games = len(remaining_dates)
                    except Exception:
                        # If schedule fetch fails, just use 0
                        pass

                enriched.append(
                    {
                        "name": name,
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
                    }
                )
                processed_count += 1
                continue

            # Skip players that return suggestions (ambiguous names)
            # Only process exact matches to avoid adding wrong players to waiver list
            skipped_count += 1

        if progress:
            progress.complete_step(
                f"[green]✓[/green] Processed {processed_count} players "
                f"([dim]{skipped_count} skipped - no NBA data or name mismatch[/dim])"
            )

        # Sort players if sort column specified, otherwise keep Yahoo order
        if sort_column:
            from tools.player.player_stats import sort_by_column

            # Normalize sort column to be case-insensitive
            sort_column_normalized = sort_column.upper().replace(" ", "_")

            # Validate sort column
            valid_columns = [
                "FG%",
                "FT%",
                "3PM",
                "PTS",
                "REB",
                "AST",
                "STL",
                "BLK",
                "TO",
                "+/-",
                "PLUS_MINUS",
                "PM",
                "USG%",
                "STARTER",
                "GAMES_STARTED",
                "TREND",
                "MIN_TREND",
                "MINUTE",
                "MIN",
                "FGM",
                "FGA",
                "FTM",
                "FTA",
            ]

            if sort_column_normalized not in valid_columns:
                self.console.print(
                    f"[yellow]Warning: Invalid sort column '{sort_column}'. "
                    f"Using Yahoo ranking instead.[/yellow]"
                )
                self.console.print(
                    f"[dim]Valid columns: {', '.join(valid_columns)}[/dim]\n"
                )
            else:
                enriched = sort_by_column(
                    enriched, sort_column_normalized, sort_ascending
                )

        return enriched[:display_count]
