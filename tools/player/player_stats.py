"""Player statistics computation module for fantasy basketball 9-category stats."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import List, Optional

from tools.player import player_fetcher


def _parse_minutes(minutes_value) -> float:
    """Parse minutes from various formats (MM:SS string or numeric)."""
    if minutes_value is None:
        return 0.0

    # If it's already a number, return it
    if isinstance(minutes_value, (int, float)):
        return float(minutes_value)

    # Convert to string and handle MM:SS format
    minutes_str = str(minutes_value).strip()
    if not minutes_str or minutes_str == "0":
        return 0.0

    # Try parsing as MM:SS format
    if ":" in minutes_str:
        try:
            parts = minutes_str.split(":")
            if len(parts) == 2:
                mins = int(parts[0])
                secs = int(parts[1])
                return mins + (secs / 60.0)
        except (ValueError, IndexError):
            pass

    # Try parsing as plain number
    try:
        return float(minutes_str)
    except ValueError:
        return 0.0


@dataclass
class PlayerStats:
    """Fantasy basketball 9-category statistics."""

    fg_pct: float
    ft_pct: float
    threes: float
    points: float
    rebounds: float
    assists: float
    steals: float
    blocks: float
    turnovers: float
    games_count: int
    # Shooting makes/attempts for display
    fgm: float
    fga: float
    ftm: float
    fta: float
    # Usage and starter stats
    usage_pct: float
    games_started: int
    # Plus-minus
    plus_minus: float
    # Minutes played
    minutes: float
    # Last game date
    last_game_date: Optional[str] = None


def _parse_stat_mode(mode: str) -> tuple[Optional[int], Optional[int]]:
    """Parse stats mode to determine number of games or days.

    Args:
        mode: 'last', 'lastN' (e.g., 'last7'), 'lastNd' (e.g., 'last7d'), or 'season'

    Returns:
        Tuple of (num_games, num_days):
        - (1, None): Last game
        - (None, None): Season (all games)
        - (N, None): Last N games
        - (None, N): Last N days from today
    """
    mode_lower = mode.lower()

    if mode_lower == "last":
        return (1, None)
    if mode_lower == "season":
        return (None, None)  # Use all available games
    if mode_lower.startswith("last"):
        # Check if it ends with 'd' for days (e.g., 'last7d')
        if mode_lower.endswith("d"):
            try:
                num_days = int(mode_lower[4:-1])  # Extract number between 'last' and 'd'
                return (None, num_days if num_days > 0 else 1)
            except (ValueError, IndexError):
                pass  # Fall through to default
        else:
            # Extract number from 'last7', 'last10', etc. (games)
            try:
                num_games = int(mode_lower[4:])
                return (num_games if num_games > 0 else 1, None)
            except (ValueError, IndexError):
                pass  # Fall through to default
    return (1, None)  # Default to last game


def compute_player_stats(
    player_id: int, mode: str, season_start: date, today: date, agg_mode: str = "avg",
    season: Optional[str] = None,
) -> Optional[PlayerStats]:
    """Compute 9-category stats from cached box scores.

    Args:
        player_id: NBA player ID
        mode: Stats calculation mode ('last', 'lastN', 'lastNd', or 'season')
        season_start: Start date of the season
        today: Current date
        agg_mode: Aggregation mode ('avg' for average, 'sum' for total)

    Returns:
        PlayerStats object with aggregated stats, or None if no games available

    Examples:
        - mode='last': Most recent game only
        - mode='last7', agg_mode='avg': Average over last 7 games
        - mode='last7d', agg_mode='avg': Average over last 7 days
        - mode='last7', agg_mode='sum': Total over last 7 games
        - mode='season', agg_mode='avg': Average over all cached games
    """
    from datetime import timedelta

    # Fetch cached games
    cached_games = player_fetcher.fetch_player_stats_from_cache(
        player_id, season_start, today, season
    )

    if not cached_games:
        return None

    # Sort by date descending (most recent first)
    sorted_games = sorted(cached_games, key=lambda g: g.get("date", ""), reverse=True)

    # Determine how many games or days to use
    num_games, num_days = _parse_stat_mode(mode)

    if num_games is None and num_days is None:
        # Season mode: use all games
        games_to_use = sorted_games
    elif num_days is not None:
        # Date-based filtering: last N days from today
        cutoff_date = today - timedelta(days=num_days)
        games_to_use = []
        for game in sorted_games:
            game_date_str = game.get("date", "")
            try:
                game_date = date.fromisoformat(game_date_str)
                if game_date >= cutoff_date:
                    games_to_use.append(game)
            except (ValueError, TypeError):
                continue
    else:
        # Game-based filtering: last N games
        games_to_use = sorted_games[:num_games]

    if not games_to_use:
        return None

    # Extract last game date
    last_game_date = games_to_use[0].get("date") if games_to_use else None

    # Aggregate stats
    total_fgm = 0.0
    total_fga = 0.0
    total_ftm = 0.0
    total_fta = 0.0
    total_3pm = 0.0
    total_pts = 0.0
    total_reb = 0.0
    total_ast = 0.0
    total_stl = 0.0
    total_blk = 0.0
    total_to = 0.0
    total_usage = 0.0
    total_plus_minus = 0.0
    total_minutes = 0.0
    games_started = 0

    games_count = len(games_to_use)

    for game in games_to_use:
        total_fgm += float(game.get("FGM", 0))
        total_fga += float(game.get("FGA", 0))
        total_ftm += float(game.get("FTM", 0))
        total_fta += float(game.get("FTA", 0))
        total_3pm += float(game.get("FG3M", 0))
        total_pts += float(game.get("PTS", 0))
        total_reb += float(game.get("REB", 0))
        total_ast += float(game.get("AST", 0))
        total_stl += float(game.get("STL", 0))
        total_blk += float(game.get("BLK", 0))
        total_to += float(game.get("TO", 0))

        # Minutes played
        total_minutes += _parse_minutes(game.get("MIN", 0))

        # Usage percentage (already a percentage from 0-1)
        usg = game.get("USG_PCT")
        if usg is not None:
            try:
                total_usage += float(usg)
            except (ValueError, TypeError):
                pass

        # Plus-minus
        pm = game.get("PLUS_MINUS")
        if pm is not None:
            try:
                total_plus_minus += float(pm)
            except (ValueError, TypeError):
                pass

        # Count games started
        is_starter = game.get("IS_STARTER", 0)
        if is_starter:
            games_started += 1

    # Calculate percentages (sum of makes / sum of attempts)
    fg_pct = (total_fgm / total_fga) if total_fga > 0 else 0.0
    ft_pct = (total_ftm / total_fta) if total_fta > 0 else 0.0

    # Calculate counting stats based on aggregation mode
    if agg_mode == "sum":
        # Use totals directly
        result_3pm = total_3pm
        result_pts = total_pts
        result_reb = total_reb
        result_ast = total_ast
        result_stl = total_stl
        result_blk = total_blk
        result_to = total_to
        result_pm = total_plus_minus
        result_minutes = total_minutes
        result_fgm = total_fgm
        result_fga = total_fga
        result_ftm = total_ftm
        result_fta = total_fta
    else:  # agg_mode == 'avg'
        # Calculate per-game averages
        result_3pm = total_3pm / games_count
        result_pts = total_pts / games_count
        result_reb = total_reb / games_count
        result_ast = total_ast / games_count
        result_stl = total_stl / games_count
        result_blk = total_blk / games_count
        result_to = total_to / games_count
        result_pm = total_plus_minus / games_count
        result_minutes = total_minutes / games_count
        result_fgm = total_fgm / games_count
        result_fga = total_fga / games_count
        result_ftm = total_ftm / games_count
        result_fta = total_fta / games_count

    # Calculate average usage percentage (always averaged)
    avg_usage = total_usage / games_count if games_count > 0 else 0.0

    return PlayerStats(
        fg_pct=fg_pct,
        ft_pct=ft_pct,
        threes=result_3pm,
        points=result_pts,
        rebounds=result_reb,
        assists=result_ast,
        steals=result_stl,
        blocks=result_blk,
        turnovers=result_to,
        games_count=games_count,
        fgm=result_fgm,
        fga=result_fga,
        ftm=result_ftm,
        fta=result_fta,
        usage_pct=avg_usage,
        games_started=games_started,
        plus_minus=result_pm,
        minutes=result_minutes,
        last_game_date=last_game_date,
    )


def sort_by_column(
    players: List[dict], column: str, ascending: bool = None
) -> List[dict]:
    """Sort players by specified stat column.

    Args:
        players: List of player dictionaries with stats
        column: Column name to sort by (case-insensitive)
        ascending: If True, sort ascending; if False, sort descending.
                  If None (default), use smart defaults based on stat category:
                    - Ascending (lower is better): TO
                    - Descending (higher is better): FG%, FT%, 3PM, PTS, REB, AST,
                      STL, BLK, MIN/MINUTE, TREND/MIN_TREND

    Returns:
        Sorted list of players

    Examples:
        >>> sort_by_column(players, 'TO')  # Ascending by default (lower TO is better)
        >>> sort_by_column(players, 'PTS')  # Descending by default (higher PTS is better)
        >>> sort_by_column(players, 'TO', ascending=False)  # Force descending
    """
    column_upper = column.upper().replace(" ", "_")

    # Define sort key functions for each column
    column_map = {
        "FG%": lambda p: p.get("stats").fg_pct if p.get("stats") else 0,
        "FT%": lambda p: p.get("stats").ft_pct if p.get("stats") else 0,
        "3PM": lambda p: p.get("stats").threes if p.get("stats") else 0,
        "PTS": lambda p: p.get("stats").points if p.get("stats") else 0,
        "REB": lambda p: p.get("stats").rebounds if p.get("stats") else 0,
        "AST": lambda p: p.get("stats").assists if p.get("stats") else 0,
        "STL": lambda p: p.get("stats").steals if p.get("stats") else 0,
        "BLK": lambda p: p.get("stats").blocks if p.get("stats") else 0,
        "TO": lambda p: (
            p.get("stats").turnovers if p.get("stats") else 999
        ),  # Higher TO is worse
        "USG%": lambda p: p.get("stats").usage_pct if p.get("stats") else 0,
        "STARTER": lambda p: p.get("stats").games_started if p.get("stats") else 0,
        "GAMES_STARTED": lambda p: (
            p.get("stats").games_started if p.get("stats") else 0
        ),
        "TREND": lambda p: p.get("trend", 0),
        "MIN_TREND": lambda p: p.get("trend", 0),  # Alias for TREND
        "MINUTE": lambda p: p.get("minutes", 0),
        "MIN": lambda p: p.get("minutes", 0),  # Alias for MINUTE
        "+/-": lambda p: p.get("stats").plus_minus if p.get("stats") else 0,
        "PLUS_MINUS": lambda p: p.get("stats").plus_minus if p.get("stats") else 0,
        "PM": lambda p: p.get("stats").plus_minus if p.get("stats") else 0,
        # Shooting volume stats (not displayed as columns but sortable)
        "FGM": lambda p: p.get("stats").fgm if p.get("stats") else 0,
        "FGA": lambda p: p.get("stats").fga if p.get("stats") else 0,
        "FTM": lambda p: p.get("stats").ftm if p.get("stats") else 0,
        "FTA": lambda p: p.get("stats").fta if p.get("stats") else 0,
    }

    key_fn = column_map.get(column_upper)

    if not key_fn:
        # Invalid column, return unsorted
        return players

    # Determine sort order based on smart defaults or user override
    if ascending is None:
        # Smart defaults: ascending for TO (lower is better), descending for all others
        reverse = column_upper != "TO"
    else:
        # User explicitly specified order
        reverse = not ascending

    return sorted(players, key=key_fn, reverse=reverse)


def calculate_league_averages_and_stddevs(
    players_stats: List[PlayerStats],
) -> tuple[dict, dict]:
    """Calculate league averages and standard deviations for 9-cat stats.

    Args:
        players_stats: List of PlayerStats objects for all players

    Returns:
        Tuple of (averages_dict, stddevs_dict) for each 9-cat stat
    """
    if not players_stats:
        return {}, {}

    # 9 categories to calculate
    categories = [
        "fg_pct",
        "ft_pct",
        "threes",
        "points",
        "rebounds",
        "assists",
        "steals",
        "blocks",
        "turnovers",
    ]

    # Collect values for each category
    values = {cat: [] for cat in categories}
    for stats in players_stats:
        values["fg_pct"].append(stats.fg_pct)
        values["ft_pct"].append(stats.ft_pct)
        values["threes"].append(stats.threes)
        values["points"].append(stats.points)
        values["rebounds"].append(stats.rebounds)
        values["assists"].append(stats.assists)
        values["steals"].append(stats.steals)
        values["blocks"].append(stats.blocks)
        values["turnovers"].append(stats.turnovers)

    # Calculate averages
    averages = {}
    for cat in categories:
        if values[cat]:
            averages[cat] = sum(values[cat]) / len(values[cat])
        else:
            averages[cat] = 0.0

    # Calculate standard deviations
    stddevs = {}
    for cat in categories:
        if len(values[cat]) > 1:
            mean = averages[cat]
            variance = sum((x - mean) ** 2 for x in values[cat]) / len(values[cat])
            stddevs[cat] = math.sqrt(variance)
        else:
            stddevs[cat] = 1.0  # Avoid division by zero

    return averages, stddevs


def compute_9cat_zscore(
    stats: PlayerStats, averages: dict, stddevs: dict
) -> float:
    """Compute total z-score across 9 fantasy basketball categories.

    For each category, z-score = (player_value - mean) / stddev
    For turnovers, the z-score is inverted (lower is better).

    Args:
        stats: PlayerStats object for the player
        averages: Dictionary of league averages for each category
        stddevs: Dictionary of league standard deviations for each category

    Returns:
        Total z-score (sum of all 9 category z-scores)
    """
    total_zscore = 0.0

    # Categories where higher is better
    positive_cats = [
        ("fg_pct", stats.fg_pct),
        ("ft_pct", stats.ft_pct),
        ("threes", stats.threes),
        ("points", stats.points),
        ("rebounds", stats.rebounds),
        ("assists", stats.assists),
        ("steals", stats.steals),
        ("blocks", stats.blocks),
    ]

    for cat_name, value in positive_cats:
        if stddevs.get(cat_name, 0) > 0:
            z = (value - averages.get(cat_name, 0)) / stddevs[cat_name]
            total_zscore += z

    # Turnovers: lower is better, so invert the z-score
    if stddevs.get("turnovers", 0) > 0:
        z = (averages.get("turnovers", 0) - stats.turnovers) / stddevs["turnovers"]
        total_zscore += z

    return total_zscore


def rank_players_by_zscore(
    players_with_stats: List[dict],
) -> List[dict]:
    """Rank players by their 9-cat z-score.

    Args:
        players_with_stats: List of dicts with 'stats' key containing PlayerStats

    Returns:
        List of players sorted by z-score (highest first), with 'z_score' and
        'rank' fields added to each player dict
    """
    # Filter to players with valid stats
    valid_players = [p for p in players_with_stats if p.get("stats") is not None]

    if not valid_players:
        return players_with_stats

    # Extract all PlayerStats objects
    all_stats = [p["stats"] for p in valid_players]

    # Calculate league averages and standard deviations
    averages, stddevs = calculate_league_averages_and_stddevs(all_stats)

    # Compute z-score for each player
    for player in valid_players:
        stats = player["stats"]
        player["z_score"] = compute_9cat_zscore(stats, averages, stddevs)

    # Players without stats get z_score of None
    for player in players_with_stats:
        if player.get("stats") is None:
            player["z_score"] = None

    # Sort by z-score descending (highest first)
    sorted_players = sorted(
        players_with_stats,
        key=lambda p: p.get("z_score") if p.get("z_score") is not None else float("-inf"),
        reverse=True,
    )

    # Assign ranks
    for idx, player in enumerate(sorted_players, start=1):
        player["rank"] = idx

    return sorted_players
