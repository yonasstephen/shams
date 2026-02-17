"""Player stats command for the Shams CLI."""

from __future__ import annotations

from datetime import date
from typing import Dict, List

from rich.console import Console
from rich.table import Table

from commands import Command, CommandError
from tools.player.player_minutes_trend import (
    MAX_SUGGESTION_LIMIT,
    SuggestionResponse,
    TrendComputation,
    normalize_season_type,
    process_minute_trend_query,
)
from tools.player.player_stats import compute_player_stats
from tools.utils.cli_common import ask
from tools.utils.render import _get_stat_color, render_suggestions_table


def parse_player_args(command: str) -> Dict[str, str]:
    """Parse arguments for the /player command."""
    parts = command.split()
    if len(parts) < 2:
        raise CommandError("Usage: /player <player name> [--season-type <type>]")

    args: Dict[str, str] = {"name": parts[1]}
    remaining = parts[2:]

    i = 0
    while i < len(remaining):
        token = remaining[i]
        if token == "--season-type":
            if i + 1 >= len(remaining):
                raise CommandError("--season-type requires a value")
            args["season_type"] = remaining[i + 1]
            i += 2
        elif token.startswith("--"):
            raise CommandError(f"Unknown option: {token}")
        else:
            args["name"] = f"{args['name']} {token}"
            i += 1

    return args


def render_player_stats_summary(
    *,
    player_name: str,
    player_id: int,
    last_game: tuple,
    last3: tuple,
    last7: tuple,
    season: tuple,
) -> Table:
    """Render comprehensive player statistics table.

    Args:
        player_name: Player's full name
        player_id: NBA player ID
        last_game: Tuple of (PlayerStats, minutes) for last game
        last3: Tuple of (PlayerStats, minutes) for last 3 games
        last7: Tuple of (PlayerStats, minutes) for last 7 games
        season: Tuple of (PlayerStats, minutes) for season

    Returns:
        Rich Table with formatted statistics
    """
    table = Table(title=f"Player Stats: {player_name} (ID {player_id})")

    # Add columns
    table.add_column("Period", justify="left", style="cyan")
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
    table.add_column("MIN", justify="right")

    # Helper to format a stats row
    def format_row(period_name: str, stats_tuple: tuple) -> list:
        stats, minutes = stats_tuple

        if not stats:
            return [
                period_name,
                "N/A",
                "N/A",
                "N/A",
                "N/A",
                "N/A",
                "N/A",
                "N/A",
                "N/A",
                "N/A",
                "N/A",
                "N/A",
                "N/A",
                "N/A",
            ]

        # Format FG% with makes/attempts
        if stats.fga > 0:
            fg_color = _get_stat_color("FG%", stats.fg_pct)
            fg_str = f"[{fg_color}]{stats.fg_pct:.1%}[/{fg_color}] ({stats.fgm:.1f}/{stats.fga:.1f})"
        else:
            fg_str = "-"

        # Format FT% with makes/attempts
        if stats.fta > 0:
            ft_color = _get_stat_color("FT%", stats.ft_pct)
            ft_str = f"[{ft_color}]{stats.ft_pct:.1%}[/{ft_color}] ({stats.ftm:.1f}/{stats.fta:.1f})"
        else:
            ft_str = "-"

        # Format counting stats with colors
        threes_color = _get_stat_color("3PM", stats.threes)
        points_color = _get_stat_color("PTS", stats.points)
        rebounds_color = _get_stat_color("REB", stats.rebounds)
        assists_color = _get_stat_color("AST", stats.assists)
        steals_color = _get_stat_color("STL", stats.steals)
        blocks_color = _get_stat_color("BLK", stats.blocks)
        turnovers_color = _get_stat_color("TO", stats.turnovers)
        plus_minus_color = _get_stat_color("+/-", stats.plus_minus)
        usage_color = _get_stat_color("USG%", stats.usage_pct)
        minutes_color = _get_stat_color("Minute", minutes)

        # Format starter column: ✓ for last game if started, count for aggregations
        if period_name == "Last Game":
            starter_str = "✓" if stats.games_started == 1 else ""
        else:
            starter_str = f"{stats.games_started}"

        return [
            period_name,
            fg_str,
            ft_str,
            f"[{threes_color}]{stats.threes:.1f}[/{threes_color}]",
            f"[{points_color}]{stats.points:.1f}[/{points_color}]",
            f"[{rebounds_color}]{stats.rebounds:.1f}[/{rebounds_color}]",
            f"[{assists_color}]{stats.assists:.1f}[/{assists_color}]",
            f"[{steals_color}]{stats.steals:.1f}[/{steals_color}]",
            f"[{blocks_color}]{stats.blocks:.1f}[/{blocks_color}]",
            f"[{turnovers_color}]{stats.turnovers:.1f}[/{turnovers_color}]",
            f"[{plus_minus_color}]{stats.plus_minus:+.1f}[/{plus_minus_color}]",
            f"[{usage_color}]{stats.usage_pct:.1%}[/{usage_color}]",
            starter_str,
            f"[{minutes_color}]{minutes:.1f}[/{minutes_color}]",
        ]

    # Add rows
    table.add_row(*format_row("Last Game", last_game))
    table.add_row(*format_row("Last 3", last3))
    table.add_row(*format_row("Last 7", last7))
    table.add_row(*format_row("Season", season))

    return table


class PlayerCommand(Command):
    """Display comprehensive player statistics across multiple time periods."""

    @property
    def name(self) -> str:
        return "/player"

    @property
    def description(self) -> str:
        return "Display player stats (last game, last 3, last 7, season average)."

    @property
    def arguments(self) -> List[Dict[str, str | bool]]:
        return [
            {
                "name": "<player_name>",
                "required": True,
                "description": "Name of the player to analyze",
            },
            {
                "name": "--season-type",
                "required": False,
                "default": "Regular Season",
                "description": "Season type (Regular Season, Playoffs, etc.)",
            },
        ]

    def execute(self, command: str) -> None:
        if self.should_show_help(command):
            self.show_help()
            return
        args = parse_player_args(command)
        season_type = normalize_season_type(args.get("season_type", ""))

        with self.console.status(
            f"[cyan]Fetching stats for {args['name']} ({season_type})...",
            spinner="dots",
        ):
            result = process_minute_trend_query(args["name"], season_type)

        if isinstance(result, SuggestionResponse):
            suggestions = list(result.suggestions)[:MAX_SUGGESTION_LIMIT]
            if not suggestions:
                self.console.print("No matching players found.", style="yellow")
                return

            self.console.print(render_suggestions_table(suggestions))
            selection = ask(
                "Select player by number",
                choices=[str(i) for i in range(1, len(suggestions) + 1)],
                show_choices=False,
            )

            chosen = suggestions[int(selection) - 1]

            with self.console.status(
                f"[cyan]Fetching stats for {chosen['full_name']}...", spinner="dots"
            ):
                final_result = process_minute_trend_query(
                    chosen["full_name"], result.season_type, suggestion_limit=1
                )

            if isinstance(final_result, TrendComputation):
                self._display_player_stats(final_result)
            else:
                self.console.print(
                    "Unexpected response; please try again.", style="red"
                )
            return

        self._display_player_stats(result)

    def _display_player_stats(self, trend_result: TrendComputation) -> None:
        """Display comprehensive player statistics."""
        player_id = trend_result.player_id
        player_name = trend_result.player_name

        # Calculate season date range
        today = date.today()
        season_start = date(today.year if today.month >= 10 else today.year - 1, 10, 21)

        # Compute stats for different time periods
        last_game_stats = compute_player_stats(player_id, "last", season_start, today)
        last3_stats = compute_player_stats(player_id, "last3", season_start, today)
        last7_stats = compute_player_stats(player_id, "last7", season_start, today)
        season_stats = compute_player_stats(player_id, "season", season_start, today)

        # Get minutes for each period by recomputing minute trends
        last_game_minutes = (
            trend_result.last_minutes if len(trend_result.logs) >= 1 else 0.0
        )

        # Compute last 3 and last 7 minute averages from game logs
        last3_minutes = (
            sum(game[1] for game in trend_result.logs[:3])
            / min(3, len(trend_result.logs))
            if trend_result.logs
            else 0.0
        )
        last7_minutes = (
            sum(game[1] for game in trend_result.logs[:7])
            / min(7, len(trend_result.logs))
            if trend_result.logs
            else 0.0
        )
        season_minutes = (
            sum(game[1] for game in trend_result.logs) / len(trend_result.logs)
            if trend_result.logs
            else 0.0
        )

        # Display the comprehensive stats table
        table = render_player_stats_summary(
            player_name=player_name,
            player_id=player_id,
            last_game=(last_game_stats, last_game_minutes),
            last3=(last3_stats, last3_minutes),
            last7=(last7_stats, last7_minutes),
            season=(season_stats, season_minutes),
        )

        self.console.print(table)

        # Display minute trend info
        trend_value = trend_result.trend
        trend_color = (
            "green" if trend_value > 0 else "red" if trend_value < 0 else "grey37"
        )
        self.console.print(
            f"\nMinute Trend: [{trend_color}]{trend_value:+.1f}[/{trend_color}] "
            f"({'↑ trending up' if trend_value > 0 else '↓ trending down' if trend_value < 0 else 'stable'} "
            f"from 3-game average)",
            style="dim",
        )
