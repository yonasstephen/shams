"""Matchup projection command for the Shams CLI."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, Iterable, List, Optional, Sequence

from rich.console import Console
from rich.table import Table

from commands import Command
from commands.league_context import LeagueContext
from tools.matchup.matchup_projection import project_matchup
from tools.utils.render import _get_stat_color
from tools.utils.yahoo import fetch_user_team_key

# Matchup rendering helper functions


def _is_ascending(stat: dict) -> bool:
    return stat.get("sort_order") in {"0", 0, "asc"}


def _is_percentage_stat(stat: dict) -> bool:
    name = (stat.get("display_name") or stat.get("name") or "").lower()
    return "%" in name


def _format_stat_value(stat: dict, value: float) -> str:
    try:
        numeric = float(value or 0.0)
    except (TypeError, ValueError):
        numeric = 0.0
    if _is_percentage_stat(stat):
        return f"{numeric * 100:.1f}%"
    return f"{numeric:.0f}"


def _points_total(points: object) -> float:
    if isinstance(points, dict):
        value = points.get("total", 0.0)
    else:
        value = points
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def render_matchup_table(
    *,
    stat_categories: Sequence[dict],
    user_current: Dict[str, float],
    user_projection: Dict[str, float],
    opponent_current: Dict[str, float],
    opponent_projection: Dict[str, float],
    user_label: str,
    opponent_label: str,
) -> Table:
    table = Table(title="Projected Category Totals")
    table.add_column("Category", style="bold")
    # Current section
    table.add_column(f"[cyan]Current[/cyan]\n{user_label}", justify="right")
    table.add_column(f"[cyan]Current[/cyan]\n{opponent_label}", justify="right")
    table.add_column("[cyan]Current[/cyan]\nMargin", justify="right")
    # Projection section
    table.add_column(f"[magenta]Projection[/magenta]\n{user_label}", justify="right")
    table.add_column(
        f"[magenta]Projection[/magenta]\n{opponent_label}", justify="right"
    )
    table.add_column("[magenta]Projection[/magenta]\nMargin", justify="right")

    for stat in stat_categories:
        stat_id = str(stat.get("stat_id"))
        if stat.get("is_only_display_stat") == 1:
            continue
        stat_name = stat.get("display_name") or stat.get("name") or stat_id

        # Get stat values
        user_proj = user_projection.get(stat_id, 0.0)
        opp_proj = opponent_projection.get(stat_id, 0.0)
        user_curr = user_current.get(stat_id, 0.0)
        opp_curr = opponent_current.get(stat_id, 0.0)

        # Calculate margins (user - opponent, positive = user winning)
        # For ascending stats (like turnovers), lower is better, so we invert
        ascending = _is_ascending(stat)
        if ascending:
            current_margin = opp_curr - user_curr
            projected_margin = opp_proj - user_proj
        else:
            current_margin = user_curr - opp_curr
            projected_margin = user_proj - opp_proj

        # Determine colors based on who's winning
        # Current colors
        if user_curr > opp_curr:
            user_curr_color = "red" if ascending else "green"
            opp_curr_color = "green" if ascending else "red"
        elif user_curr < opp_curr:
            user_curr_color = "green" if ascending else "red"
            opp_curr_color = "red" if ascending else "green"
        else:
            user_curr_color = opp_curr_color = "yellow"

        # Projected colors
        if user_proj > opp_proj:
            user_proj_color = "red" if ascending else "green"
            opp_proj_color = "green" if ascending else "red"
        elif user_proj < opp_proj:
            user_proj_color = "green" if ascending else "red"
            opp_proj_color = "red" if ascending else "green"
        else:
            user_proj_color = opp_proj_color = "yellow"

        # Format stat values with shooting volume for FG% and FT%
        is_percentage = _is_percentage_stat(stat)

        # Check if this is FG% or FT% to add shooting volume
        if stat_name == "FG%":
            user_fgm_curr = user_current.get("_FGM", 0.0)
            user_fga_curr = user_current.get("_FGA", 0.0)
            opp_fgm_curr = opponent_current.get("_FGM", 0.0)
            opp_fga_curr = opponent_current.get("_FGA", 0.0)
            user_fgm_proj = user_projection.get("_FGM", 0.0)
            user_fga_proj = user_projection.get("_FGA", 0.0)
            opp_fgm_proj = opponent_projection.get("_FGM", 0.0)
            opp_fga_proj = opponent_projection.get("_FGA", 0.0)

            user_curr_str = f"[{user_curr_color}]{_format_stat_value(stat, user_curr)} ({user_fgm_curr:.0f}/{user_fga_curr:.0f})[/{user_curr_color}]"
            opp_curr_str = f"[{opp_curr_color}]{_format_stat_value(stat, opp_curr)} ({opp_fgm_curr:.0f}/{opp_fga_curr:.0f})[/{opp_curr_color}]"
            user_proj_str = f"[{user_proj_color}]{_format_stat_value(stat, user_proj)} ({user_fgm_proj:.0f}/{user_fga_proj:.0f})[/{user_proj_color}]"
            opp_proj_str = f"[{opp_proj_color}]{_format_stat_value(stat, opp_proj)} ({opp_fgm_proj:.0f}/{opp_fga_proj:.0f})[/{opp_proj_color}]"
        elif stat_name == "FT%":
            user_ftm_curr = user_current.get("_FTM", 0.0)
            user_fta_curr = user_current.get("_FTA", 0.0)
            opp_ftm_curr = opponent_current.get("_FTM", 0.0)
            opp_fta_curr = opponent_current.get("_FTA", 0.0)
            user_ftm_proj = user_projection.get("_FTM", 0.0)
            user_fta_proj = user_projection.get("_FTA", 0.0)
            opp_ftm_proj = opponent_projection.get("_FTM", 0.0)
            opp_fta_proj = opponent_projection.get("_FTA", 0.0)

            user_curr_str = f"[{user_curr_color}]{_format_stat_value(stat, user_curr)} ({user_ftm_curr:.0f}/{user_fta_curr:.0f})[/{user_curr_color}]"
            opp_curr_str = f"[{opp_curr_color}]{_format_stat_value(stat, opp_curr)} ({opp_ftm_curr:.0f}/{opp_fta_curr:.0f})[/{opp_curr_color}]"
            user_proj_str = f"[{user_proj_color}]{_format_stat_value(stat, user_proj)} ({user_ftm_proj:.0f}/{user_fta_proj:.0f})[/{user_proj_color}]"
            opp_proj_str = f"[{opp_proj_color}]{_format_stat_value(stat, opp_proj)} ({opp_ftm_proj:.0f}/{opp_fta_proj:.0f})[/{opp_proj_color}]"
        else:
            user_curr_str = f"[{user_curr_color}]{_format_stat_value(stat, user_curr)}[/{user_curr_color}]"
            opp_curr_str = f"[{opp_curr_color}]{_format_stat_value(stat, opp_curr)}[/{opp_curr_color}]"
            user_proj_str = f"[{user_proj_color}]{_format_stat_value(stat, user_proj)}[/{user_proj_color}]"
            opp_proj_str = f"[{opp_proj_color}]{_format_stat_value(stat, opp_proj)}[/{opp_proj_color}]"

        # Format margins
        if is_percentage:
            current_margin_str = f"{current_margin * 100:+.1f}%"
            projected_margin_str = f"{projected_margin * 100:+.1f}%"
        else:
            current_margin_str = f"{current_margin:+.2f}"
            projected_margin_str = f"{projected_margin:+.2f}"

        current_margin_color = (
            "green"
            if current_margin > 0
            else ("red" if current_margin < 0 else "yellow")
        )
        projected_margin_color = (
            "green"
            if projected_margin > 0
            else ("red" if projected_margin < 0 else "yellow")
        )

        table.add_row(
            stat_name,
            # Current section
            user_curr_str,
            opp_curr_str,
            f"[{current_margin_color}]{current_margin_str}[/{current_margin_color}]",
            # Projection section
            user_proj_str,
            opp_proj_str,
            f"[{projected_margin_color}]{projected_margin_str}[/{projected_margin_color}]",
        )

    return table


def render_team_points_summary(
    user_label: str,
    user_points: object,
    user_projected_points: object,
    opponent_label: str,
    opponent_points: object,
    opponent_projected_points: object,
) -> Table:
    user_total = _points_total(user_points)
    opp_total = _points_total(opponent_points)
    user_proj_total = _points_total(user_projected_points)
    opp_proj_total = _points_total(opponent_projected_points)

    # Color based on current score
    if user_total > opp_total:
        user_color, opp_color = "green", "red"
    elif user_total < opp_total:
        user_color, opp_color = "red", "green"
    else:
        user_color = opp_color = "yellow"

    # Color for projected score
    if user_proj_total > opp_proj_total:
        user_proj_color, opp_proj_color = "green", "red"
    elif user_proj_total < opp_proj_total:
        user_proj_color, opp_proj_color = "red", "green"
    else:
        user_proj_color = opp_proj_color = "yellow"

    table = Table.grid(expand=False)
    table.add_row(
        f"[bold {user_color}]{user_label}[/bold {user_color}]: {user_total:.0f} "
        f"([{user_proj_color}]{user_proj_total:.0f}[/{user_proj_color}])"
        f"  |  [bold {opp_color}]{opponent_label}[/bold {opp_color}]: {opp_total:.0f} "
        f"([{opp_proj_color}]{opp_proj_total:.0f}[/{opp_proj_color}])"
    )
    return table


def render_roster_contributions(
    *,
    stat_categories: Sequence[dict],
    player_contributions: Dict[str, Dict[str, float]],
    player_names: Dict[str, str],
    player_total_games: Optional[Dict[str, int]] = None,
    player_remaining_games: Optional[Dict[str, int]] = None,
    player_shooting: Optional[Dict[str, dict]] = None,
) -> Optional[Table]:
    if not player_contributions:
        return None

    player_table = Table(title="User Roster Contributions")
    player_table.add_column("Player")

    # Add Games column if game data is provided
    if player_total_games is not None and player_remaining_games is not None:
        player_table.add_column("Games")

    for stat in stat_categories:
        stat_id = str(stat.get("stat_id"))
        if stat.get("is_only_display_stat") == 1:
            continue
        stat_name = stat.get("abbr") or stat.get("display_name") or stat_id
        player_table.add_column(stat_name)

    for key, stats in player_contributions.items():
        row = [player_names.get(key, key)]

        # Add games with color coding based on remaining games
        if player_total_games is not None and player_remaining_games is not None:
            total_games = player_total_games.get(key, 0)
            remaining_games = player_remaining_games.get(key, 0)
            # Color code based on remaining games
            if remaining_games == 0:
                games_color = "dim"  # Dark gray for zero games remaining
            elif remaining_games >= 4:
                games_color = "green"
            elif remaining_games > 2:
                games_color = "yellow"
            else:
                games_color = "red"
            row.append(
                f"[{games_color}]({remaining_games}/{total_games})[/{games_color}]"
            )

        # Get shooting stats for this player
        shooting = (player_shooting or {}).get(key, {})

        for stat in stat_categories:
            stat_id = str(stat.get("stat_id"))
            if stat.get("is_only_display_stat") == 1:
                continue

            value = stats.get(stat_id, 0.0)

            # Special formatting for FG% and FT% to include makes/attempts
            if stat_id == "5" and shooting:  # FG%
                fgm = shooting.get("fgm", 0)
                fga = shooting.get("fga", 0)
                if fgm > 0 or fga > 0:
                    row.append(f"{value * 100:.1f}% ({fgm:.0f}/{fga:.0f})")
                else:
                    row.append(_format_stat_value(stat, value))
            elif stat_id == "8" and shooting:  # FT%
                ftm = shooting.get("ftm", 0)
                fta = shooting.get("fta", 0)
                if ftm > 0 or fta > 0:
                    row.append(f"{value * 100:.1f}% ({ftm:.0f}/{fta:.0f})")
                else:
                    row.append(_format_stat_value(stat, value))
            else:
                row.append(_format_stat_value(stat, value))

        player_table.add_row(*row)

    return player_table


def render_league_matchups(
    *,
    league_name: str,
    week: Optional[object],
    matchups: Iterable[dict],
) -> Iterable[Table]:
    for matchup in matchups:
        teams = matchup.get("teams", [])
        if len(teams) != 2:
            continue
        team_a, team_b = teams
        header = Table.grid()
        subtitle = f"Week {matchup.get('week', week)} | {matchup.get('week_start')} - {matchup.get('week_end')}"
        title = f"{team_a.get('team_name', 'Team A')} vs {team_b.get('team_name', 'Team B')}"
        header.add_row(f"[bold]{league_name}[/bold] :: {title} :: {subtitle}")
        yield header

        yield render_team_points_summary(
            team_a.get("team_name", "Team A"),
            team_a.get("team_points"),
            team_a.get("projected_team_points"),
            team_b.get("team_name", "Team B"),
            team_b.get("team_points"),
            team_b.get("projected_team_points"),
        )

        yield render_matchup_table(
            stat_categories=matchup.get("stat_categories", []),
            user_current=team_a.get("current", {}),
            user_projection=team_a.get("projection", {}),
            opponent_current=team_b.get("current", {}),
            opponent_projection=team_b.get("projection", {}),
            user_label=team_a.get("team_name", "Team A"),
            opponent_label=team_b.get("team_name", "Team B"),
        )


def render_daily_contributions(
    *,
    stat_categories: Sequence[dict],
    daily_contributions: Dict[str, Dict[str, Dict[str, float]]],
    player_names: Dict[str, str],
    week_start: str,
    week_end: str,
) -> Optional[Table]:
    """Render day-by-day breakdown of player stat contributions.

    Args:
        stat_categories: List of stat category metadata
        daily_contributions: Dict[player_key, Dict[date_str, Dict[stat_id, float]]]
        player_names: Dict[player_key, player_name]
        week_start: Week start date in ISO format
        week_end: Week end date in ISO format

    Returns:
        Rich Table showing daily stats per player, or None if no data
    """
    if not daily_contributions:
        return None

    # Parse date range
    start_date = date.fromisoformat(week_start)
    end_date = date.fromisoformat(week_end)
    today = date.today()

    # Generate list of remaining dates (today onwards)
    remaining_dates = []
    current = max(start_date, today)
    while current <= end_date:
        remaining_dates.append(current.isoformat())
        current += timedelta(days=1)

    if not remaining_dates:
        return None

    # Create table
    table = Table(title="Daily Player Contributions (Remaining Games)")
    table.add_column("Player", style="cyan", no_wrap=True)

    # Add date columns
    for date_str in remaining_dates:
        date_obj = date.fromisoformat(date_str)
        # Format as "Mon 10/28"
        day_name = date_obj.strftime("%a")
        month_day = date_obj.strftime("%-m/%-d")
        table.add_column(f"{day_name}\n{month_day}", justify="left")

    # Build stat ID to abbreviation mapping
    stat_abbr_map = {}
    stat_name_map = {}
    for stat in stat_categories:
        stat_id = str(stat.get("stat_id"))
        if stat.get("is_only_display_stat") == 1:
            continue
        abbr = stat.get("abbr") or stat.get("display_name") or stat_id
        name = stat.get("display_name") or stat.get("name") or abbr
        stat_abbr_map[stat_id] = abbr
        stat_name_map[stat_id] = name

    # Sort players by total games remaining (most games first)
    def player_game_count(player_key: str) -> int:
        daily = daily_contributions.get(player_key, {})
        return sum(1 for d in remaining_dates if d in daily)

    sorted_players = sorted(
        daily_contributions.keys(), key=player_game_count, reverse=True
    )

    # Track daily totals for summary row
    daily_totals: Dict[str, Dict[str, float]] = {d: {} for d in remaining_dates}
    daily_game_counts: Dict[str, int] = {d: 0 for d in remaining_dates}

    # Add player rows
    for player_key in sorted_players:
        player_name = player_names.get(player_key, player_key)
        daily_stats = daily_contributions.get(player_key, {})

        row = [player_name]

        for date_str in remaining_dates:
            if date_str not in daily_stats:
                row.append("[dim]-[/dim]")
                continue

            stats = daily_stats[date_str]
            daily_game_counts[date_str] += 1

            # Collect stats by category
            stat_values = {}
            for stat_id, abbr in stat_abbr_map.items():
                stat_name = stat_name_map.get(stat_id, "")
                value = stats.get(stat_id, 0.0)

                # Add to daily totals
                if stat_id not in daily_totals[date_str]:
                    daily_totals[date_str][stat_id] = 0.0

                # For counting stats, accumulate
                if "%" not in stat_name:
                    daily_totals[date_str][stat_id] += value

                stat_values[abbr] = value

            # Track shooting volume in daily totals
            for key in ["_FGM", "_FGA", "_FTM", "_FTA"]:
                if key not in daily_totals[date_str]:
                    daily_totals[date_str][key] = 0.0
                daily_totals[date_str][key] += stats.get(key, 0.0)

            # Format as: 25/8/7 FTA:5 80% 2s2b 2TO
            # With color coding based on thresholds
            parts = []

            # 1. PTS/REB/AST (always show, with color coding)
            pts = stat_values.get("PTS", 0.0)
            reb = stat_values.get("REB", 0.0)
            ast = stat_values.get("AST", 0.0)

            pts_color = _get_stat_color("PTS", pts)
            reb_color = _get_stat_color("REB", reb)
            ast_color = _get_stat_color("AST", ast)

            parts.append(
                f"[{pts_color}]{pts:.0f}[/{pts_color}]/"
                f"[{reb_color}]{reb:.0f}[/{reb_color}]/"
                f"[{ast_color}]{ast:.0f}[/{ast_color}]"
            )

            # 2. FG% (just percentage, no attempts breakdown)
            fgm = stats.get("_FGM", 0.0)
            fga = stats.get("_FGA", 0.0)
            # Calculate FG% from daily FGM/FGA, not season average
            fg_pct = (fgm / fga) if fga > 0 else 0.0
            if fg_pct > 0:
                fg_color = _get_stat_color("FG%", fg_pct)
                parts.append(f"FG:[{fg_color}]{fg_pct*100:.0f}%[/{fg_color}]")

            # 3. 3PTM if meaningful
            threes = stat_values.get("3PTM", stat_values.get("3PM", 0.0))
            if threes >= 1:
                threes_color = _get_stat_color("3PM", threes)
                parts.append(f"[{threes_color}]{threes:.0f}-3pt[/{threes_color}]")

            # 4. FT with attempts and percentage
            ftm = stats.get("_FTM", 0.0)
            fta = stats.get("_FTA", 0.0)
            # Calculate FT% from daily FTM/FTA, not season average
            ft_pct = (ftm / fta) if fta > 0 else 0.0
            if fta > 0:
                ft_color = _get_stat_color("FT%", ft_pct)
                parts.append(
                    f"FTA:{fta:.0f} [{ft_color}]{ft_pct*100:.0f}%[/{ft_color}]"
                )

            # 5. Steals and blocks combined (if meaningful)
            stl = stat_values.get("STL", stat_values.get("ST", 0.0))
            blk = stat_values.get("BLK", 0.0)
            defensive = []
            if stl >= 0.5:
                stl_color = _get_stat_color("STL", stl)
                defensive.append(f"[{stl_color}]{stl:.0f}s[/{stl_color}]")
            if blk >= 0.5:
                blk_color = _get_stat_color("BLK", blk)
                defensive.append(f"[{blk_color}]{blk:.0f}b[/{blk_color}]")
            if defensive:
                parts.append("".join(defensive))

            # 6. Turnovers (if meaningful)
            to = stat_values.get("TO", 0.0)
            if to >= 0.5:
                to_color = _get_stat_color("TO", to)
                parts.append(f"[{to_color}]{to:.0f}TO[/{to_color}]")

            if parts:
                row.append(" ".join(parts))
            else:
                row.append("[dim]0[/dim]")

        table.add_row(*row)

    # Add separator and totals row
    if daily_totals:
        table.add_section()
        totals_row = ["[bold]Team Total[/bold]"]

        for date_str in remaining_dates:
            game_count = daily_game_counts.get(date_str, 0)
            totals = daily_totals.get(date_str, {})

            if game_count == 0:
                totals_row.append("[dim]-[/dim]")
                continue

            # Collect total stats
            total_values = {}
            for stat_id, abbr in stat_abbr_map.items():
                total_values[abbr] = totals.get(stat_id, 0.0)

            # Format totals: [bold]5g[/bold] 125/40/35 FTA:25 80% 10-3pt 10s5b
            # With color coding
            parts = [f"[bold]{game_count}g[/bold]"]

            # PTS/REB/AST - use per-game averages for color thresholds
            pts = total_values.get("PTS", 0.0)
            reb = total_values.get("REB", 0.0)
            ast = total_values.get("AST", 0.0)

            # Color based on per-game averages
            pts_per_game = pts / game_count if game_count > 0 else 0
            reb_per_game = reb / game_count if game_count > 0 else 0
            ast_per_game = ast / game_count if game_count > 0 else 0

            pts_color = _get_stat_color("PTS", pts_per_game)
            reb_color = _get_stat_color("REB", reb_per_game)
            ast_color = _get_stat_color("AST", ast_per_game)

            parts.append(
                f"[{pts_color}]{pts:.0f}[/{pts_color}]/"
                f"[{reb_color}]{reb:.0f}[/{reb_color}]/"
                f"[{ast_color}]{ast:.0f}[/{ast_color}]"
            )

            # FG%
            total_fgm = totals.get("_FGM", 0.0)
            total_fga = totals.get("_FGA", 0.0)
            if total_fga > 0:
                team_fg_pct = total_fgm / total_fga
                fg_color = _get_stat_color("FG%", team_fg_pct)
                parts.append(f"FG:[{fg_color}]{team_fg_pct*100:.0f}%[/{fg_color}]")

            # 3PTM
            threes = total_values.get("3PTM", total_values.get("3PM", 0.0))
            if threes >= 1:
                threes_per_game = threes / game_count if game_count > 0 else 0
                threes_color = _get_stat_color("3PM", threes_per_game)
                parts.append(f"[{threes_color}]{threes:.0f}-3pt[/{threes_color}]")

            # FT shooting
            total_ftm = totals.get("_FTM", 0.0)
            total_fta = totals.get("_FTA", 0.0)
            if total_fta > 0:
                team_ft_pct = total_ftm / total_fta
                ft_color = _get_stat_color("FT%", team_ft_pct)
                parts.append(
                    f"FTA:{total_fta:.0f} [{ft_color}]{team_ft_pct*100:.0f}%[/{ft_color}]"
                )

            # Steals and blocks
            stl = total_values.get("STL", total_values.get("ST", 0.0))
            blk = total_values.get("BLK", 0.0)
            defensive = []
            if stl >= 0.5:
                stl_per_game = stl / game_count if game_count > 0 else 0
                stl_color = _get_stat_color("STL", stl_per_game)
                defensive.append(f"[{stl_color}]{stl:.0f}s[/{stl_color}]")
            if blk >= 0.5:
                blk_per_game = blk / game_count if game_count > 0 else 0
                blk_color = _get_stat_color("BLK", blk_per_game)
                defensive.append(f"[{blk_color}]{blk:.0f}b[/{blk_color}]")
            if defensive:
                parts.append("".join(defensive))

            # Turnovers
            to = total_values.get("TO", 0.0)
            if to >= 0.5:
                to_per_game = to / game_count if game_count > 0 else 0
                to_color = _get_stat_color("TO", to_per_game)
                parts.append(f"[{to_color}]{to:.0f}TO[/{to_color}]")

            totals_row.append(" ".join(parts))

        table.add_row(*totals_row)

    return table


class MatchupCommand(Command):
    """Show current matchup with projected category outcomes."""

    def __init__(self, console: Console, league_context: LeagueContext) -> None:
        super().__init__(console)
        self.league_context = league_context

    @property
    def name(self) -> str:
        return "/matchup"

    @property
    def description(self) -> str:
        return "Show current matchup plus projected category outcomes."

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
                "name": "-w, --week",
                "required": False,
                "default": "current week",
                "description": "Week number to view (e.g., -w 2)",
            },
        ]

    def execute(self, command: str) -> None:
        if self.should_show_help(command):
            self.show_help()
            return
        parts = command.split()

        # Parse optional week flag
        week = None
        i = 0
        while i < len(parts):
            if parts[i] in ("-w", "--week") and i + 1 < len(parts):
                try:
                    week = int(parts[i + 1])
                except ValueError:
                    self.console.print(
                        f"Invalid week number: {parts[i + 1]}", style="red"
                    )
                    return
                i += 2
            else:
                i += 1

        league_key = self.league_context.resolve_league_key(parts)
        if not league_key:
            return

        with self.console.status("[cyan]Fetching matchup data...", spinner="dots"):
            try:
                team_key = fetch_user_team_key(league_key)
            except Exception as err:  # noqa: BLE001
                self.console.print(f"Unable to determine user team: {err}", style="red")
                return

        with self.console.status("[cyan]Computing projections...", spinner="dots"):
            try:
                projection = project_matchup(league_key, team_key, week=week)
            except Exception as err:  # noqa: BLE001
                self.console.print(f"Error projecting matchup: {err}", style="red")
                return

        user_team = projection.get("user_team", {})
        opponent_team = projection.get("opponent_team", {})
        week = projection.get("week")
        self.console.print(
            f"[bold green]Matchup projection (Week {week}):[/bold green]"
        )
        self.console.print(
            f"{projection.get('week_start')} to {projection.get('week_end')}"
        )

        points_table = render_team_points_summary(
            user_team.get("team_name", "User"),
            projection.get("user_team_points"),
            projection.get("user_projected_team_points"),
            opponent_team.get("team_name", "Opponent"),
            projection.get("opponent_team_points"),
            projection.get("opponent_projected_team_points"),
        )
        self.console.print(points_table)

        matchup_table = render_matchup_table(
            stat_categories=projection.get("stat_categories", []),
            user_current=projection.get("user_current", {}),
            user_projection=projection.get("user_projection", {}),
            opponent_current=projection.get("opponent_current", {}),
            opponent_projection=projection.get("opponent_projection", {}),
            user_label=user_team.get("team_name", "User"),
            opponent_label=opponent_team.get("team_name", "Opponent"),
        )
        self.console.print(matchup_table)

        contribution_table = render_roster_contributions(
            stat_categories=projection.get("stat_categories", []),
            player_contributions=projection.get("player_contributions", {}),
            player_names=projection.get("player_names", {}),
            player_total_games=projection.get("player_total_games", {}),
            player_remaining_games=projection.get("player_remaining_games", {}),
            player_shooting=projection.get("player_shooting", {}),
        )
        if contribution_table:
            self.console.print(contribution_table)

        daily_table = render_daily_contributions(
            stat_categories=projection.get("stat_categories", []),
            daily_contributions=projection.get("daily_contributions", {}),
            player_names=projection.get("player_names", {}),
            week_start=projection.get("week_start", ""),
            week_end=projection.get("week_end", ""),
        )
        if daily_table:
            self.console.print(daily_table)
