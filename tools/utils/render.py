"""Rendering helpers using Rich."""

from __future__ import annotations

from typing import Sequence

from rich.console import Console
from rich.table import Table

from tools.utils.stat_thresholds import get_thresholds

console = Console()


def _get_stat_color(stat_name: str, value: float) -> str:  # pylint: disable=too-many-return-statements
    """Return color based on stat thresholds for fantasy basketball stats.

    This function provides consistent color coding across all stat tables.
    Thresholds are configurable via environment variables in .env file.

    Args:
        stat_name: Name of the stat (e.g., "3PM", "PTS", "FG%")
        value: Numeric value of the stat

    Returns:
        Rich color string ("white", "yellow", "green", or "red")

    Default Color Thresholds (customizable via .env):
        3PM: <2 white, 2-3 yellow, ≥4 green
        PTS: <5 white, 5-12 yellow, ≥13 green
        REB: <5 white, 5-8 yellow, ≥9 green
        AST: <3 white, 3-5 yellow, ≥6 green
        STL/BLK: <2 white, 2 yellow, ≥3 green
        TO: <2 green, 2-3 yellow, ≥4 red (inverse: lower is better)
        FG%: <30% red, 30-49% yellow, ≥50% green
        FT%: <60% red, 60-79% yellow, ≥80% green
        USG%: <15% white, 15-24% yellow, ≥25% green
        Minute: <10 white, 10-17 yellow, ≥18 green
    """
    thresholds = get_thresholds()

    if stat_name == "3PM":
        if value < thresholds.threes_yellow_min:
            return "white"
        if value < thresholds.threes_green_min:
            return "yellow"
        return "green"
    if stat_name == "PTS":
        if value < thresholds.pts_yellow_min:
            return "white"
        if value < thresholds.pts_green_min:
            return "yellow"
        return "green"
    if stat_name == "REB":
        if value < thresholds.reb_yellow_min:
            return "white"
        if value < thresholds.reb_green_min:
            return "yellow"
        return "green"
    if stat_name == "AST":
        if value < thresholds.ast_yellow_min:
            return "white"
        if value < thresholds.ast_green_min:
            return "yellow"
        return "green"
    if stat_name == "STL":
        if value < thresholds.stl_yellow_min:
            return "white"
        if value < thresholds.stl_green_min:
            return "yellow"
        return "green"
    if stat_name == "BLK":
        if value < thresholds.blk_yellow_min:
            return "white"
        if value < thresholds.blk_green_min:
            return "yellow"
        return "green"
    if stat_name == "TO":
        if value < thresholds.to_green_max:
            return "green"
        if value < thresholds.to_yellow_max:
            return "yellow"
        return "red"
    if stat_name == "FG%":
        if value < thresholds.fg_pct_red_max:
            return "red"
        if value < thresholds.fg_pct_yellow_max:
            return "yellow"
        return "green"
    if stat_name == "FT%":
        if value < thresholds.ft_pct_red_max:
            return "red"
        if value < thresholds.ft_pct_yellow_max:
            return "yellow"
        return "green"
    if stat_name == "USG%":
        if value < thresholds.usg_pct_yellow_min:
            return "white"
        if value < thresholds.usg_pct_green_min:
            return "yellow"
        return "green"
    if stat_name == "Minute":
        if value < thresholds.min_yellow_min:
            return "white"
        if value < thresholds.min_green_min:
            return "yellow"
        return "green"
    if stat_name in ("+/-", "PLUS_MINUS"):
        # Plus-minus: positive is good (green), negative is bad (red)
        if value > 5:
            return "green"
        if value > 0:
            return "yellow"
        if value >= -5:
            return "white"
        return "red"
    return "white"


def render_suggestions_table(suggestions: Sequence[dict]) -> Table:
    table = Table(title="Multiple matches found")
    table.add_column("#", justify="center")
    table.add_column("Player", justify="left")
    for idx, player in enumerate(suggestions, start=1):
        table.add_row(str(idx), player["full_name"])
    return table
