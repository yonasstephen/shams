"""Projection utilities for Yahoo H2H matchups."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from tools.boxscore import boxscore_cache
from tools.player import player_fetcher
from tools.player.player_stats import compute_player_stats
from tools.schedule import schedule_fetcher
from tools.utils.yahoo import (
    determine_current_week,
    extract_team_id,
    fetch_league_scoreboard,
    fetch_league_stat_categories,
    fetch_matchup_context,
    fetch_team_roster_for_date,
    fetch_team_stats_for_week,
    fetch_user_team_key,
)

logger = logging.getLogger(__name__)


def _current_season() -> str:
    """Return the active NBA season string derived from today's date (e.g. '2025-26').

    Oct–Dec  → first year of the new season  (e.g. Oct 2025 → 2025-26)
    Jan–Sep  → second year of the current season (e.g. Feb 2026 → 2025-26)
    """
    today = date.today()
    year = today.year if today.month >= 10 else today.year - 1
    return f"{year}-{str(year + 1)[-2:]}"


def _date_range(start: date, end: date) -> Iterable[date]:
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def _stat_sort_order(stat: Dict[str, object]) -> int:
    try:
        return int(stat.get("sort_order", 0))
    except (TypeError, ValueError):
        return 0


def _is_category_desc(stat: Dict[str, object]) -> bool:
    return stat.get("sort_order", "") in {"0", 0, "asc"}


def _player_is_active(player: dict) -> bool:
    """Check if player is in an active roster position.

    Active means not in BN (bench), IL (injured list), IL+ (injured list+), or DNP (did not play).
    """
    selected_position = player.get("selected_position")
    if isinstance(selected_position, dict):
        position = selected_position.get("position")
    elif selected_position is not None:
        # If it's a string or other type, use it directly
        position = str(selected_position) if selected_position else None
    else:
        position = None

    # Inactive positions - bench and injured list
    # Note: DNP was mentioned in docs but missing from original set
    inactive_positions = {"BN", "IL", "IL+", "DNP", ""}

    if not position:
        # Missing position data - treat as inactive to be safe
        player_name = player.get("name", {})
        if isinstance(player_name, dict):
            full_name = player_name.get("full", "Unknown")
        else:
            full_name = str(player_name)
        logger.debug(f"Player {full_name} has no position data, treating as inactive")
        return False

    is_active = position not in inactive_positions

    # Log IL+ players specifically since that's the bug being reported
    if position in {"IL", "IL+"}:
        player_name = player.get("name", {})
        if isinstance(player_name, dict):
            full_name = player_name.get("full", "Unknown")
        else:
            full_name = str(player_name)
        logger.debug(
            f"Player {full_name} is in {position} position - marked as inactive"
        )

    return is_active


def _player_key(player: dict) -> Optional[str]:
    return player.get("player_key")


def _collect_roster(
    league_key: str, team_id: int, start: date, end: date
) -> Dict[str, List[dict]]:
    rosters: Dict[str, List[dict]] = {}
    today = date.today()
    logger.info(
        f"Collecting roster for team {team_id} from {start.isoformat()} to {end.isoformat()} (today: {today.isoformat()})"
    )

    last_fetched: List[dict] = []
    for current in _date_range(start, end):
        if current > today:
            # Yahoo's API rejects future-date roster requests.
            # Reuse the most recent fetched roster as the standing projection lineup.
            rosters[current.isoformat()] = last_fetched
            logger.debug(
                f"  Date {current.isoformat()}: future date, reusing roster from {today.isoformat()} ({len(last_fetched)} players)"
            )
            continue

        players = fetch_team_roster_for_date(league_key, team_id, current)
        all_players = []
        for entry in players:
            player = entry
            if isinstance(entry, dict):
                player = entry.get("player", entry)

            # Handle both dict and yfpy Player objects
            if not isinstance(player, dict):
                # Convert yfpy Player object to dict
                if hasattr(player, "serialized"):
                    player = player.serialized()
                elif hasattr(player, "__dict__"):
                    player = player.__dict__
                else:
                    continue

            # Include ALL players (active and benched) for display purposes
            # Team totals will only count active players
            all_players.append(player)
        rosters[current.isoformat()] = all_players
        last_fetched = all_players
        logger.debug(
            f"  Date {current.isoformat()}: {len(all_players)} players fetched"
        )

    logger.info(f"Roster collection complete: {len(rosters)} dates fetched")
    return rosters


def _build_optimized_player_active_dates(
    league_key: str,
    roster: Dict[str, List[dict]],
    week_start: date,
    week_end: date,
    season: str = "2025-26",
) -> Tuple[Dict[str, set], Dict[str, str]]:
    """Build mapping of player_key -> set of dates where player is active, using optimized roster positions.

    This function uses the roster optimizer to determine optimal positions for maximizing active players.
    Player rankings are used as a tie-breaker when multiple players have the same flexibility.

    Args:
        league_key: Yahoo league key
        roster: Dict mapping date strings to lists of player dicts
        week_start: Start date of week
        week_end: End date of week
        season: NBA season string

    Returns:
        Tuple of (active_dates_map, optimized_positions_by_date)
        - active_dates_map: Dict mapping player keys to sets of date strings where they are active
        - optimized_positions_by_date: Dict mapping date -> player_key -> position for per-day optimization
    """
    from tools.matchup import roster_optimizer
    from tools.utils import league_cache, player_index, yahoo
    from tools.utils.player_utils import get_player_eligible_positions

    # Get league roster settings
    league_roster_positions = yahoo.fetch_and_cache_league_roster_positions(league_key)
    
    # Load player rankings for tie-breaking during optimization
    # This maps player_key -> rank (1 = best player)
    player_ranks = player_index.get_all_player_ranks(league_key)
    if player_ranks:
        logger.info(f"Loaded {len(player_ranks)} player rankings for optimization tie-breaking")
    else:
        logger.debug("No player rankings available, using default tie-breaking (player_key)")

    if not league_roster_positions:
        logger.warning("Could not fetch league roster positions, falling back to non-optimized mode")
        # Return empty optimized positions map to indicate fallback to non-optimized mode
        return _build_player_active_dates(roster), {}

    # Deduplicate players and collect their eligible positions
    unique_players: Dict[str, dict] = {}
    for players in roster.values():
        for player in players:
            player_key = _player_key(player)
            if player_key and player_key not in unique_players:
                unique_players[player_key] = player

    # Extract eligible positions for each player from already-fetched roster data
    # PERFORMANCE NOTE: No additional API calls are made here!
    # Yahoo's get_team_roster_player_info_by_date() already includes eligible_positions field
    players_for_optimizer = []
    missing_eligibility_count = 0
    
    for player_key, player in unique_players.items():
        # Get eligible positions from player object (already fetched from Yahoo API)
        # This is just a dictionary lookup - no API call
        eligible_positions = get_player_eligible_positions(player)

        # If not in player object, try to load from cache (fallback - should be very rare)
        if not eligible_positions:
            missing_eligibility_count += 1
            player_name = player.get("name", {}).get("full", "")
            nba_id = player_fetcher.player_id_lookup(player_name)
            if nba_id:
                cached_eligibility = boxscore_cache.load_player_eligibility(nba_id, season)
                if cached_eligibility:
                    eligible_positions = cached_eligibility
                    logger.debug(f"Loaded cached eligibility for {player_name}: {eligible_positions}")

        # If still no eligible positions, assign empty list (will go to BN)
        if not eligible_positions:
            logger.debug(f"No eligible positions for player {player_key}, will be assigned to BN")
            eligible_positions = []

        players_for_optimizer.append({
            "player_key": player_key,
            "eligible_positions": eligible_positions,
        })
    
    # Log if any players are missing eligibility data (should be rare)
    if missing_eligibility_count > 0:
        logger.info(
            f"Note: {missing_eligibility_count}/{len(unique_players)} players missing eligible_positions in roster data. "
            f"This is expected for some player types and does not impact performance."
        )

    # Build Yahoo positions per day from roster
    yahoo_positions_by_date: Dict[str, Dict[str, str]] = {}  # date -> player_key -> position
    for date_str, players in roster.items():
        yahoo_positions_by_date[date_str] = {}
        for player in players:
            player_key = _player_key(player)
            if not player_key:
                continue
            
            # Extract position from Yahoo roster
            selected_position = player.get("selected_position")
            if isinstance(selected_position, dict):
                position = selected_position.get("position", "")
            else:
                position = selected_position if selected_position else ""
            
            yahoo_positions_by_date[date_str][player_key] = position or ""

    # Build player schedules: map player_key -> set of dates with games
    player_schedules: Dict[str, Set[str]] = {}
    for player_key, player in unique_players.items():
        player_name = player.get("name", {}).get("full", "")
        nba_id = player_fetcher.player_id_lookup(player_name)
        if nba_id:
            schedule = schedule_fetcher.fetch_player_upcoming_games_from_cache(
                nba_id, week_start.isoformat(), week_end.isoformat(), season
            )
            if schedule.game_dates:
                player_schedules[player_key] = set(schedule.game_dates)
            else:
                player_schedules[player_key] = set()
        else:
            player_schedules[player_key] = set()

    # Optimize roster PER DAY to maximize active players each day
    player_active_dates: Dict[str, set] = {}
    optimized_positions_by_date: Dict[str, Dict[str, str]] = {}  # date -> player_key -> position
    
    # Collect all dates in the roster
    all_dates = sorted(roster.keys())
    
    logger.info(f"Optimizing roster per-day for {len(all_dates)} dates")

    for date_str in all_dates:
        # Get Yahoo positions for this date
        yahoo_positions_today = yahoo_positions_by_date.get(date_str, {})
        
        # Get set of players who are actually on the roster today (not dropped)
        players_on_roster_today = set(yahoo_positions_today.keys())
        
        # Identify players in IL/IL+ positions - these should NOT be optimized
        players_in_il_today: Dict[str, str] = {}  # player_key -> IL position
        for player_key, position in yahoo_positions_today.items():
            if position in ["IL", "IL+"]:
                players_in_il_today[player_key] = position
        
        # Determine which players have games on this specific date (excluding IL/IL+ players)
        # IMPORTANT: Only consider players who are actually on the roster for this date
        players_with_games_today: Set[str] = set()
        for player_key, game_dates in player_schedules.items():
            if (date_str in game_dates 
                and player_key not in players_in_il_today
                and player_key in players_on_roster_today):
                players_with_games_today.add(player_key)
        
        if players_in_il_today:
            logger.debug(f"  {date_str}: {len(players_with_games_today)} players with games, {len(players_in_il_today)} in IL/IL+")
        else:
            logger.debug(f"  {date_str}: {len(players_with_games_today)} players with games")

        # Filter players_for_optimizer to only include players on roster today
        # This prevents dropped players from being assigned positions for future dates
        players_for_optimizer_today = [
            p for p in players_for_optimizer
            if p.get("player_key") in players_on_roster_today
        ]

        # Run optimizer for this specific date (excluding IL/IL+ players)
        # Pass player_ranks for tie-breaking when players have same flexibility
        optimized_positions_today = roster_optimizer.optimize_roster_positions(
            players_for_optimizer_today,
            league_roster_positions,
            players_with_games_today,
            player_ranks=player_ranks,
        )
        
        # Merge optimized positions with IL/IL+ positions (IL/IL+ takes precedence)
        final_positions_today = {**optimized_positions_today, **players_in_il_today}
        
        optimized_positions_by_date[date_str] = final_positions_today

        # Track which players are active on this date
        inactive_positions = {"BN", "IL", "IL+"}
        for player_key, position in final_positions_today.items():
            if position not in inactive_positions:
                if player_key not in player_active_dates:
                    player_active_dates[player_key] = set()
                player_active_dates[player_key].add(date_str)

    return player_active_dates, optimized_positions_by_date


def _build_player_active_dates(roster: Dict[str, List[dict]]) -> Dict[str, set]:
    """Build mapping of player_key -> set of dates where player was ACTIVE.

    Active means on roster AND not in BN, IL, IL+, DNP positions.

    NOTE: Due to Yahoo API limitations, historical roster queries may return the current
    roster for all dates. This function attempts to detect recently added players by checking
    for ownership/transaction data.

    Args:
        roster: Dict mapping date strings to lists of player dicts

    Returns:
        Dict mapping player keys to sets of date strings where they were active
    """
    player_active_dates: Dict[str, set] = {}
    player_first_seen: Dict[str, str] = {}  # Track when each player first appeared

    # Get today for filtering
    today = date.today().isoformat()

    # Collect all dates sorted
    sorted_dates = sorted(roster.keys())

    for date_str in sorted_dates:
        players = roster.get(date_str, [])
        for player in players:
            player_key = _player_key(player)
            if not player_key:
                continue

            # Track first date we see this player
            if player_key not in player_first_seen:
                player_first_seen[player_key] = date_str

            player_name = player.get("name", {})
            if isinstance(player_name, dict):
                full_name = player_name.get("full", "Unknown")
            else:
                full_name = str(player_name)

            # Get position for logging
            selected_position = player.get("selected_position")
            if isinstance(selected_position, dict):
                position = selected_position.get("position", "N/A")
            else:
                position = selected_position if selected_position else "N/A"

            is_active = _player_is_active(player)

            # Check for ownership data to determine when player was actually added
            ownership = player.get("ownership")
            if ownership:
                # Serialize if needed
                if not isinstance(ownership, dict) and hasattr(ownership, "serialized"):
                    ownership = ownership.serialized()
                elif not isinstance(ownership, dict) and hasattr(ownership, "__dict__"):
                    ownership = ownership.__dict__

                if isinstance(ownership, dict):
                    # Check for transaction data within ownership
                    # Note: The structure varies, but we're looking for acquisition date/time
                    logger.debug(f"Player {full_name} ownership data: {ownership}")

            # Yahoo API limitation workaround:
            # If this is the first date we see the player AND it's today or later,
            # don't count stats from earlier dates this week
            first_seen_date = player_first_seen.get(player_key, date_str)
            if first_seen_date >= today and date_str < today:
                continue

            # Log position info for all players (can be filtered by log level)
            logger.debug(
                f"Date {date_str}: {full_name:30} | Position: {position:5} | Active: {is_active}"
            )

            if is_active:
                if player_key not in player_active_dates:
                    player_active_dates[player_key] = set()
                player_active_dates[player_key].add(date_str)

    return player_active_dates


def _season_stat_map(player: dict) -> Dict[str, float]:
    """Extract season stat averages from a player dict."""
    stats = player.get("player_stats", {})

    # Serialize if it's a yfpy object
    if not isinstance(stats, dict) and hasattr(stats, "serialized"):
        stats = stats.serialized()
    elif not isinstance(stats, dict) and hasattr(stats, "__dict__"):
        stats = stats.__dict__

    stat_entries = stats.get("stats") if isinstance(stats, dict) else stats

    result: Dict[str, float] = {}
    for stat in stat_entries or []:
        # Serialize stat if it's a yfpy object
        if not isinstance(stat, dict):
            if hasattr(stat, "serialized"):
                stat = stat.serialized()
            elif hasattr(stat, "__dict__"):
                stat = stat.__dict__

        stat_obj = stat.get("stat") if isinstance(stat, dict) else stat

        # Serialize stat_obj if it's a yfpy object
        if not isinstance(stat_obj, dict):
            if hasattr(stat_obj, "serialized"):
                stat_obj = stat_obj.serialized()
            elif hasattr(stat_obj, "__dict__"):
                stat_obj = stat_obj.__dict__

        if not isinstance(stat_obj, dict):
            continue

        stat_id = str(stat_obj.get("stat_id"))
        try:
            value = float(stat_obj.get("value", 0.0))
        except (TypeError, ValueError):
            value = 0.0
        result[stat_id] = value

    return result


def _build_stat_name_to_cache_mapping() -> Dict[str, str]:
    """Map stat names/abbreviations to boxscore cache field names (for season stats - lowercase)."""
    return {
        # Percentage stats
        "FG%": "fg_pct",
        "FT%": "ft_pct",
        # Counting stats - both abbreviations and full names
        "3PTM": "threes",
        "3PM": "threes",
        "3-Point Baskets Made": "threes",
        "PTS": "points",
        "Points": "points",
        "REB": "rebounds",
        "Rebounds": "rebounds",
        "AST": "assists",
        "Assists": "assists",
        "ST": "steals",
        "STL": "steals",
        "Steals": "steals",
        "BLK": "blocks",
        "Blocks": "blocks",
        "TO": "turnovers",
        "Turnovers": "turnovers",
    }


def _build_stat_name_to_game_field_mapping() -> Dict[str, str]:
    """Map stat names/abbreviations to boxscore game field names (UPPERCASE)."""
    return {
        # Percentage stats - stored but not used directly
        "FG%": "FG_PCT",
        "FT%": "FT_PCT",
        # Counting stats
        "3PTM": "FG3M",
        "3PM": "FG3M",
        "PTS": "PTS",
        "REB": "REB",
        "AST": "AST",
        "ST": "STL",
        "STL": "STL",
        "BLK": "BLK",
        "TO": "TO",
    }


def _project_player_stats(
    league_key: str,
    player: dict,
    game_dates: Sequence[str],
    stat_meta: Sequence[Dict[str, object]],
    season: str = "2025-26",
    projection_mode: str = "season",
) -> Dict[str, float]:
    """Project a player's stats for the given game dates using boxscore cache.

    Args:
        league_key: Yahoo league key
        player: Player dict from roster
        game_dates: List of game date strings to project for
        stat_meta: Stat category metadata
        season: NBA season string
        projection_mode: One of "season", "last3", "last7", "last7d", "last30d"

    Returns:
        Dict mapping stat_id to projected value
    """
    key = _player_key(player)
    stat_ids = [
        str(s.get("stat_id")) for s in stat_meta if s.get("is_only_display_stat") != 1
    ]

    if not key or not game_dates:
        return {stat_id: 0.0 for stat_id in stat_ids}

    # Get player name and look up NBA ID
    player_name = player.get("name", {}).get("full", "")
    nba_id = player_fetcher.player_id_lookup(player_name)

    if not nba_id:
        return {stat_id: 0.0 for stat_id in stat_ids}

    # Determine which computation method to use based on projection_mode
    if projection_mode == "season":
        # Fast path: use pre-computed season stats from cache
        cached_stats = boxscore_cache.load_player_season_stats(nba_id, season)

        if not cached_stats:
            return {stat_id: 0.0 for stat_id in stat_ids}

        # Build mapping from stat names to cache fields
        name_to_cache = _build_stat_name_to_cache_mapping()

        # Map stats dynamically based on stat category metadata
        projected = {}
        games_count = len(game_dates)

        for stat in stat_meta:
            stat_id = str(stat.get("stat_id"))
            if stat.get("is_only_display_stat") == 1:
                continue

            # Get stat name (try display_name, then name, then abbreviation)
            stat_name = (
                stat.get("display_name") or stat.get("name") or stat.get("abbr", "")
            )

            # Look up cache field name
            cache_field = name_to_cache.get(stat_name)
            if not cache_field:
                projected[stat_id] = 0.0
                continue

            # Get value from cache
            value = cached_stats.get(cache_field, 0.0)

            # Check if this is a percentage stat
            is_percentage = "%" in stat_name

            if is_percentage:
                # For percentage stats, don't multiply by games
                projected[stat_id] = value
            else:
                # For counting stats, multiply by number of games
                projected[stat_id] = value * games_count

        return projected
    else:
        # Compute stats using compute_player_stats for other modes
        season_start = schedule_fetcher.get_season_start_date(season)
        today = date.today()

        # Compute per-game averages using selected mode
        player_stats = compute_player_stats(
            player_id=nba_id,
            mode=projection_mode,
            season_start=season_start,
            today=today,
            agg_mode="avg",  # Always get per-game averages for projection
            season=season,
        )

        if not player_stats:
            # Fallback to season stats if computation fails
            return _project_player_stats(
                league_key, player, game_dates, stat_meta, season, "season"
            )

        # Map PlayerStats to stat_ids
        projected = {}
        games_count = len(game_dates)

        for stat in stat_meta:
            stat_id = str(stat.get("stat_id"))
            if stat.get("is_only_display_stat") == 1:
                continue

            stat_name = (
                stat.get("display_name") or stat.get("name") or stat.get("abbr", "")
            )
            is_percentage = "%" in stat_name

            # Map stat names to PlayerStats attributes
            if stat_name == "FG%":
                projected[stat_id] = player_stats.fg_pct
            elif stat_name == "FT%":
                projected[stat_id] = player_stats.ft_pct
            elif stat_name in ["3PTM", "3PM", "3-Point Baskets Made"]:
                projected[stat_id] = player_stats.threes * (
                    1 if is_percentage else games_count
                )
            elif stat_name in ["PTS", "Points"]:
                projected[stat_id] = player_stats.points * games_count
            elif stat_name in ["REB", "Rebounds"]:
                projected[stat_id] = player_stats.rebounds * games_count
            elif stat_name in ["AST", "Assists"]:
                projected[stat_id] = player_stats.assists * games_count
            elif stat_name in ["ST", "STL", "Steals"]:
                projected[stat_id] = player_stats.steals * games_count
            elif stat_name in ["BLK", "Blocks"]:
                projected[stat_id] = player_stats.blocks * games_count
            elif stat_name in ["TO", "Turnovers"]:
                projected[stat_id] = player_stats.turnovers * games_count
            else:
                projected[stat_id] = 0.0

        return projected


def _project_team(
    league_key: str,
    roster: Dict[str, List[dict]],
    matchup_start: date,
    matchup_end: date,
    stat_meta: Sequence[Dict[str, object]],
    season: str = "2025-26",
    projection_mode: str = "season",
    optimize_roster: bool = False,
) -> Dict[str, float]:
    """Project team stats by combining actual results + remaining projections.

    Only projects stats for games on dates when players are in active positions
    (not BN, IL, IL+).

    For past weeks (matchup_end < today), uses actual game data only.
    For current/future weeks, combines actual stats from games played + projections
    for remaining games. This ensures projected totals are always >= current totals.

    Args:
        league_key: Yahoo league key
        roster: Player roster by date
        matchup_start: Start date of matchup
        matchup_end: End date of matchup
        stat_meta: Stat category metadata
        season: NBA season string
        projection_mode: One of "season", "last3", "last7", "last7d", "last30d"
        optimize_roster: If True, optimize roster positions for maximum active players

    Returns:
        Dict mapping stat_id to projected team total (current + remaining)
    """
    today = date.today()

    # For past weeks, use actual game data instead of projections
    if matchup_end < today:
        # This is a past week - use actual data
        (current_contributions, _, current_player_shooting, _, _, _) = (
            _aggregate_current_week_player_contributions(
                league_key, roster, matchup_start, matchup_end, stat_meta, season
            )
        )
        # Sum up the actual contributions
        return _sum_player_contributions_to_team_total(
            current_contributions, current_player_shooting, stat_meta
        )

    # For current/future weeks, combine actual stats from games played + remaining projections
    # This ensures projected totals are always >= current totals
    logger.info(
        f"Projecting team for current/future week: {matchup_start.isoformat()} to {matchup_end.isoformat()}"
    )

    # 1. Get actual contributions from games already played this week
    (current_contributions, _, current_player_shooting, _, _, _) = (
        _aggregate_current_week_player_contributions(
            league_key, roster, matchup_start, matchup_end, stat_meta, season
        )
    )
    current_totals = _sum_player_contributions_to_team_total(
        current_contributions, current_player_shooting, stat_meta
    )
    logger.info(
        f"Current totals calculated from actual games played: {len(current_contributions)} players"
    )

    # 2. Get remaining projections for games yet to be played
    (proj_contributions, _, _, _, proj_player_shooting, _, _, _) = (
        _aggregate_projected_contributions(
            league_key,
            roster,
            matchup_start,
            matchup_end,
            stat_meta,
            season,
            projection_mode,
            optimize_roster,
        )
    )
    remaining_totals = _sum_player_contributions_to_team_total(
        proj_contributions, proj_player_shooting, stat_meta
    )
    logger.info(
        f"Remaining projections calculated: {len(proj_contributions)} players"
    )

    # 3. Combine current + remaining for total projection
    stat_ids = [
        str(s.get("stat_id")) for s in stat_meta if s.get("is_only_display_stat") != 1
    ]

    # Find percentage stat IDs dynamically
    percentage_stat_ids = set()
    for stat in stat_meta:
        if stat.get("is_only_display_stat") == 1:
            continue
        stat_name = stat.get("display_name") or stat.get("name") or ""
        if "%" in stat_name:
            percentage_stat_ids.add(str(stat.get("stat_id")))

    # Combine stats
    totals = {stat_id: 0.0 for stat_id in stat_ids}

    # For counting stats: add current + remaining
    for stat_id in stat_ids:
        if stat_id not in percentage_stat_ids:
            totals[stat_id] = current_totals.get(stat_id, 0.0) + remaining_totals.get(
                stat_id, 0.0
            )

    # For percentage stats: recalculate from combined shooting volume
    # Combine FGM/FGA and FTM/FTA from both current and remaining
    total_fgm = current_totals.get("_FGM", 0.0) + remaining_totals.get("_FGM", 0.0)
    total_fga = current_totals.get("_FGA", 0.0) + remaining_totals.get("_FGA", 0.0)
    total_ftm = current_totals.get("_FTM", 0.0) + remaining_totals.get("_FTM", 0.0)
    total_fta = current_totals.get("_FTA", 0.0) + remaining_totals.get("_FTA", 0.0)

    # Calculate percentage values from combined shooting volume
    for stat in stat_meta:
        stat_id = str(stat.get("stat_id"))
        if stat.get("is_only_display_stat") == 1:
            continue
        stat_name = stat.get("display_name") or stat.get("name") or ""

        if stat_name == "FG%":
            totals[stat_id] = (total_fgm / total_fga) if total_fga > 0 else 0.0
        elif stat_name == "FT%":
            totals[stat_id] = (total_ftm / total_fta) if total_fta > 0 else 0.0

    # Add shooting volume stats as special keys
    totals["_FGM"] = total_fgm
    totals["_FGA"] = total_fga
    totals["_FTM"] = total_ftm
    totals["_FTA"] = total_fta

    logger.info(f"Combined projection complete. Total projection calculated.")
    return totals


def _extract_team_stats(team_data: dict) -> Dict[str, float]:
    stats_container = team_data.get("team_stats")
    if hasattr(stats_container, "serialized"):
        stats_container = stats_container.serialized()
    stats_list = []
    if isinstance(stats_container, dict):
        stats_list = stats_container.get("stats", [])
    elif hasattr(stats_container, "stats"):
        stats_list = stats_container.stats

    result: Dict[str, float] = {}
    for stat_entry in stats_list or []:
        stat_obj = stat_entry
        if isinstance(stat_entry, dict):
            stat_obj = stat_entry.get("stat", stat_entry)
        elif hasattr(stat_entry, "serialized"):
            stat_obj = stat_entry.serialized()

        if not isinstance(stat_obj, dict):
            continue
        stat_id = str(stat_obj.get("stat_id"))
        try:
            value = float(stat_obj.get("value", 0.0))
        except (TypeError, ValueError):
            value = 0.0
        result[stat_id] = value
    return result


def _extract_player_stats(player: dict) -> Dict[str, float]:
    stats_container = player.get("player_stats", {})
    if hasattr(stats_container, "serialized"):
        stats_container = stats_container.serialized()
    stat_entries = (
        stats_container.get("stats")
        if isinstance(stats_container, dict)
        else stats_container
    )
    result: Dict[str, float] = {}
    for stat_entry in stat_entries or []:
        stat_obj = stat_entry
        if isinstance(stat_entry, dict):
            stat_obj = stat_entry.get("stat", stat_entry)
        elif hasattr(stat_entry, "serialized"):
            stat_obj = stat_entry.serialized()
        if not isinstance(stat_obj, dict):
            continue
        stat_id = str(stat_obj.get("stat_id"))
        try:
            value = float(stat_obj.get("value", 0.0))
        except (TypeError, ValueError):
            value = 0.0
        result[stat_id] = value
    return result


def _extract_team_points(team_data: dict) -> Dict[str, float]:
    points_container = team_data.get("team_points", {})
    if hasattr(points_container, "serialized"):
        points_container = points_container.serialized()
    if not isinstance(points_container, dict):
        return {}

    result: Dict[str, float] = {}
    for key, value in points_container.items():
        if key == "coverage_type":
            continue
        try:
            result[key] = float(value)
        except (TypeError, ValueError):
            continue
    return result


def _aggregate_player_contributions(
    roster: Dict[str, List[dict]]
) -> Tuple[Dict[str, Dict[str, float]], Dict[str, str]]:
    contributions: Dict[str, Dict[str, float]] = {}
    player_names: Dict[str, str] = {}
    for date_players in roster.values():
        for player in date_players:
            key = _player_key(player)
            if not key:
                continue
            stats = _extract_player_stats(player)
            if key not in contributions:
                contributions[key] = dict(stats)
                player_names[key] = player.get("name", {}).get("full", key)
            else:
                for stat_id, value in stats.items():
                    contributions[key][stat_id] = (
                        contributions[key].get(stat_id, 0.0) + value
                    )
    return contributions, player_names


def _aggregate_current_week_player_contributions(
    _league_key: str,
    roster: Dict[str, List[dict]],
    week_start: date,
    week_end: date,
    stat_meta: Sequence[Dict[str, object]],
    _season: str = "2025-26",
    optimize_roster: bool = False,
) -> Tuple[
    Dict[str, Dict[str, float]],
    Dict[str, str],
    Dict[str, dict],
    Dict[str, bool],
    Dict[str, int],
    Dict[str, Optional[int]],
]:
    """Calculate actual current week contributions for each player from boxscore cache.

    Only counts stats from games played on dates when the player was on the roster
    AND in an active position (not BN, IL, IL+).

    Args:
        _league_key: Yahoo league key
        roster: Player roster by date
        week_start: Start date of week
        week_end: End date of week
        stat_meta: Stat category metadata
        _season: NBA season string
        optimize_roster: If True, optimize roster positions for maximum active players

    Returns:
        Tuple of (contributions, player_names, player_shooting, is_on_roster_today, player_games_played, player_ids) where:
        - contributions: actual accumulated stats from games played this week (not projections)
        - player_names: player key to name mapping
        - player_shooting: shooting stats per player
        - is_on_roster_today: whether each player is still on the roster today
        - player_games_played: number of games played this week while in active roster spot
        - player_ids: player key to NBA player ID mapping
    """
    from tools.player import player_fetcher

    stat_ids = [
        str(s.get("stat_id")) for s in stat_meta if s.get("is_only_display_stat") != 1
    ]

    contributions: Dict[str, Dict[str, float]] = {}
    player_names: Dict[str, str] = {}
    player_shooting: Dict[str, dict] = {}
    is_on_roster_today: Dict[str, bool] = {}
    player_games_played: Dict[str, int] = {}
    player_ids: Dict[str, Optional[int]] = {}

    # Get today to determine what games have been played
    today = date.today()

    # Get the most recent roster to check which players are on the team
    # Use today's roster or the most recent past date (don't use future dates)
    todays_roster_players = set()
    if roster:
        # Get the most recent date that's <= today (don't use future roster dates)
        today_str = today.isoformat()
        past_dates = [d for d in roster.keys() if d <= today_str]
        if not past_dates:
            # All roster dates are in the future, use the earliest one
            most_recent_date = min(roster.keys())
        else:
            most_recent_date = max(past_dates)
        for player in roster[most_recent_date]:
            player_key = _player_key(player)
            if player_key:
                todays_roster_players.add(player_key)

    # Only fetch games from the week that have actually been played
    # If today is before week_start, no games have been played yet
    if today < week_start:
        # Week hasn't started yet, return zeros for everyone
        unique_players: Dict[str, dict] = {}
        for players in roster.values():
            for player in players:
                player_key = _player_key(player)
                if player_key and player_key not in unique_players:
                    unique_players[player_key] = player

        for player_key, player in unique_players.items():
            player_names[player_key] = player.get("name", {}).get("full", "")
            contributions[player_key] = {stat_id: 0.0 for stat_id in stat_ids}
            player_shooting[player_key] = {}
            is_on_roster_today[player_key] = player_key in todays_roster_players
            player_games_played[player_key] = 0
            player_ids[player_key] = None

        return (
            contributions,
            player_names,
            player_shooting,
            is_on_roster_today,
            player_games_played,
            player_ids,
        )

    # If today is the first day of the week, only include completed games from yesterday
    # (to avoid including late-night games from previous week that might be cached with today's date)
    if today == week_start:
        # Week just started, no games have been completed yet today
        yesterday = today - timedelta(days=1)
        if yesterday < week_start:
            # Yesterday was before the week started, so no games yet
            unique_players: Dict[str, dict] = {}
            for players in roster.values():
                for player in players:
                    player_key = _player_key(player)
                    if player_key and player_key not in unique_players:
                        unique_players[player_key] = player

            for player_key, player in unique_players.items():
                player_names[player_key] = player.get("name", {}).get("full", "")
                contributions[player_key] = {stat_id: 0.0 for stat_id in stat_ids}
                player_shooting[player_key] = {}
                is_on_roster_today[player_key] = player_key in todays_roster_players
                player_ids[player_key] = None

            return (
                contributions,
                player_names,
                player_shooting,
                is_on_roster_today,
                {},
                player_ids,
            )

    # Calculate the actual date range for games played this week
    # Use yesterday as the cutoff to avoid late-night games cached with today's date
    yesterday = today - timedelta(days=1)
    fetch_end = min(week_end, yesterday)

    # If we haven't had any completed days in the week yet, return zeros
    if fetch_end < week_start:
        unique_players: Dict[str, dict] = {}
        for players in roster.values():
            for player in players:
                player_key = _player_key(player)
                if player_key and player_key not in unique_players:
                    unique_players[player_key] = player

        for player_key, player in unique_players.items():
            player_names[player_key] = player.get("name", {}).get("full", "")
            contributions[player_key] = {stat_id: 0.0 for stat_id in stat_ids}
            player_shooting[player_key] = {}
            is_on_roster_today[player_key] = player_key in todays_roster_players
            player_games_played[player_key] = 0
            player_ids[player_key] = None

        return (
            contributions,
            player_names,
            player_shooting,
            is_on_roster_today,
            player_games_played,
            player_ids,
        )

    # Deduplicate players
    unique_players: Dict[str, dict] = {}
    for players in roster.values():
        for player in players:
            player_key = _player_key(player)
            if player_key and player_key not in unique_players:
                unique_players[player_key] = player

    # Build mapping from stat names to game field names (UPPERCASE)
    stat_name_to_field = _build_stat_name_to_game_field_mapping()

    # Build mapping of which dates each player was active
    if optimize_roster:
        # Unpack tuple - we only need active_dates_map here, ignore optimized_positions_by_date
        active_dates_map, _ = _build_optimized_player_active_dates(_league_key, roster, week_start, week_end, _season)
    else:
        active_dates_map = _build_player_active_dates(roster)

    for player_key, player in unique_players.items():
        player_name = player.get("name", {}).get("full", "")
        player_names[player_key] = player_name
        is_on_roster_today[player_key] = player_key in todays_roster_players

        nba_id = player_fetcher.player_id_lookup(player_name)
        player_ids[player_key] = nba_id
        if not nba_id:
            contributions[player_key] = {stat_id: 0.0 for stat_id in stat_ids}
            player_shooting[player_key] = {}
            player_games_played[player_key] = 0
            continue

        # Get dates when this player was active (on roster and not benched/IL)
        active_dates = active_dates_map.get(player_key, set())

        # Fetch only games that have actually been played (from week_start up to and including today)
        games_this_week = player_fetcher.fetch_player_stats_from_cache(
            nba_id, week_start, fetch_end, _season
        )

        # Debug: Check if player has games but no active dates (indicating they're in IL/BN all week)
        if games_this_week and not active_dates:
            logger.warning(
                f"Player {player_name} has {len(games_this_week)} games this week but zero active dates. "
                f"This suggests they were in BN/IL/IL+ for all dates in the week."
            )

        if not games_this_week:
            contributions[player_key] = {stat_id: 0.0 for stat_id in stat_ids}
            player_shooting[player_key] = {}
            player_games_played[player_key] = 0
            continue

        # Aggregate stats from games played this week
        totals = {stat_id: 0.0 for stat_id in stat_ids}
        total_fgm = 0.0
        total_fga = 0.0
        total_ftm = 0.0
        total_fta = 0.0

        games_counted = 0
        for game in games_this_week:
            # Only count games from dates when player was active on roster
            game_date = game.get("date", "")
            if game_date not in active_dates:
                continue

            games_counted += 1

            total_fgm += float(game.get("FGM", 0))
            total_fga += float(game.get("FGA", 0))
            total_ftm += float(game.get("FTM", 0))
            total_fta += float(game.get("FTA", 0))

            # Accumulate counting stats
            for stat in stat_meta:
                stat_id = str(stat.get("stat_id"))
                if stat.get("is_only_display_stat") == 1:
                    continue

                stat_name = (
                    stat.get("display_name") or stat.get("name") or stat.get("abbr", "")
                )
                field_name = stat_name_to_field.get(stat_name)

                if not field_name:
                    continue

                # For counting stats, sum them up
                if "%" not in stat_name:
                    totals[stat_id] += float(game.get(field_name, 0))

        # Calculate percentage stats from totals
        for stat in stat_meta:
            stat_id = str(stat.get("stat_id"))
            if stat.get("is_only_display_stat") == 1:
                continue

            stat_name = (
                stat.get("display_name") or stat.get("name") or stat.get("abbr", "")
            )

            if stat_name == "FG%":
                totals[stat_id] = (total_fgm / total_fga) if total_fga > 0 else 0.0
            elif stat_name == "FT%":
                totals[stat_id] = (total_ftm / total_fta) if total_fta > 0 else 0.0

        contributions[player_key] = totals
        player_shooting[player_key] = {
            "fgm": total_fgm,
            "fga": total_fga,
            "fg_pct": (total_fgm / total_fga) if total_fga > 0 else 0.0,
            "ftm": total_ftm,
            "fta": total_fta,
            "ft_pct": (total_ftm / total_fta) if total_fta > 0 else 0.0,
        }
        player_games_played[player_key] = games_counted

    return (
        contributions,
        player_names,
        player_shooting,
        is_on_roster_today,
        player_games_played,
        player_ids,
    )


def _compute_daily_player_contributions(
    _league_key: str,
    roster: Dict[str, List[dict]],
    week_start: date,
    week_end: date,
    stat_meta: Sequence[Dict[str, object]],
    season: str = "2025-26",
    optimized_positions_by_date: Optional[Dict[str, Dict[str, str]]] = None,
) -> Tuple[
    Dict[str, Dict[str, Dict[str, float]]],
    Dict[str, str],
    Dict[str, Dict[str, str]],
    Dict[str, Optional[int]],
]:
    """Calculate per-player per-day stat projections for remaining days.

    Only includes projections for dates where the player is on the roster AND in an
    active position (not BN, IL, IL+).

    Args:
        _league_key: Yahoo league key
        roster: Player roster by date  
        week_start: Start date of week
        week_end: End date of week
        stat_meta: Stat category metadata
        season: NBA season string
        optimized_positions_by_date: If provided, use these optimized positions (date -> player -> position) instead of Yahoo positions

    Returns:
        Tuple of (remaining_days_projection, player_names, player_positions, player_ids) where:
        - remaining_days_projection: Dict[player_key, Dict[date_str, Dict[stat_id, float]]]
        - player_names: Dict[player_key, str]
        - player_positions: Dict[player_key, Dict[date_str, str]] - position for each date
        - player_ids: Dict[player_key, Optional[int]] - player key to NBA player ID mapping
    """
    # Build mapping from stat names to cache fields
    name_to_cache = _build_stat_name_to_cache_mapping()

    remaining_days_projection: Dict[str, Dict[str, Dict[str, float]]] = {}
    player_names: Dict[str, str] = {}
    player_positions: Dict[str, Dict[str, str]] = {}
    player_ids: Dict[str, Optional[int]] = {}

    # Build mapping of which dates each player was active
    # If optimized positions provided, use those to determine active dates
    # Otherwise, use Yahoo positions from roster
    if optimized_positions_by_date:
        # Build active dates from optimized positions
        player_active_dates: Dict[str, set] = {}
        inactive_positions = {"BN", "IL", "IL+"}
        for date_str, positions_map in optimized_positions_by_date.items():
            for player_key, position in positions_map.items():
                if position not in inactive_positions:
                    if player_key not in player_active_dates:
                        player_active_dates[player_key] = set()
                    player_active_dates[player_key].add(date_str)
    else:
        # Use non-optimized active dates from Yahoo roster
        player_active_dates = _build_player_active_dates(roster)

    # Build mapping of player positions per date from Yahoo (for fallback)
    player_positions_by_date: Dict[str, Dict[str, str]] = {}
    for date_str, players in roster.items():
        for player in players:
            player_key = _player_key(player)
            if not player_key:
                continue

            # Get position
            selected_position = player.get("selected_position")
            if isinstance(selected_position, dict):
                position = selected_position.get("position", "")
            else:
                position = selected_position if selected_position else ""

            if player_key not in player_positions_by_date:
                player_positions_by_date[player_key] = {}
            player_positions_by_date[player_key][date_str] = position or ""

    # Deduplicate players
    unique_players: Dict[str, dict] = {}
    for players in roster.values():
        for player in players:
            player_key = _player_key(player)
            if player_key and player_key not in unique_players:
                unique_players[player_key] = player

    for player_key, player in unique_players.items():
        player_name = player.get("name", {}).get("full", "")
        player_names[player_key] = player_name

        nba_id = player_fetcher.player_id_lookup(player_name)
        player_ids[player_key] = nba_id
        if not nba_id:
            remaining_days_projection[player_key] = {}
            player_positions[player_key] = {}
            continue

        schedule = schedule_fetcher.fetch_player_upcoming_games_from_cache(
            nba_id, week_start.isoformat(), week_end.isoformat(), season
        )

        if not schedule.game_dates:
            remaining_days_projection[player_key] = {}
            player_positions[player_key] = {}
            continue

        # Load season stats from cache
        cached_stats = boxscore_cache.load_player_season_stats(nba_id, season)
        if not cached_stats:
            remaining_days_projection[player_key] = {}
            player_positions[player_key] = {}
            continue

        # For each game date, only project if player is ON THE ROSTER for that date
        # This includes both active positions and inactive positions (BN, IL, IL+)
        remaining_days_projection[player_key] = {}
        player_positions[player_key] = {}
        active_dates = player_active_dates.get(player_key, set())

        # Get the dates when this player was actually on the roster
        roster_dates = player_positions_by_date.get(player_key, {})

        for game_date in schedule.game_dates:
            # Only process dates when the player is on the roster
            if game_date not in roster_dates:
                continue

            # Store position for this date
            # If optimized positions provided, use those; otherwise use Yahoo positions
            if optimized_positions_by_date and game_date in optimized_positions_by_date:
                position = optimized_positions_by_date[game_date].get(player_key, "BN")
            else:
                position = roster_dates[game_date]
            player_positions[player_key][game_date] = position

            # Check if player is active (not benched/IL) for this date
            is_active = game_date in active_dates

            daily_stats = {}

            if is_active:
                # Player is active - include actual projections
                for stat in stat_meta:
                    stat_id = str(stat.get("stat_id"))
                    if stat.get("is_only_display_stat") == 1:
                        continue

                    # Get stat name and look up cache field
                    stat_name = (
                        stat.get("display_name")
                        or stat.get("name")
                        or stat.get("abbr", "")
                    )
                    cache_field = name_to_cache.get(stat_name)

                    if not cache_field:
                        daily_stats[stat_id] = 0.0
                        continue

                    # Get per-game value from cache
                    value = cached_stats.get(cache_field, 0.0)
                    daily_stats[stat_id] = value

                # Add shooting volume stats (FGM/FGA, FTM/FTA) as special keys
                daily_stats["_FGM"] = cached_stats.get("fgm", 0.0)
                daily_stats["_FGA"] = cached_stats.get("fga", 0.0)
                daily_stats["_FTM"] = cached_stats.get("ftm", 0.0)
                daily_stats["_FTA"] = cached_stats.get("fta", 0.0)
            else:
                # Player is inactive (BN, IL, IL+) - add empty marker so frontend knows there's a game
                # This allows the frontend to display the inactive position status
                daily_stats["_INACTIVE"] = 1

            # Add entry for dates where player is on roster (whether active or inactive)
            remaining_days_projection[player_key][game_date] = daily_stats
    return remaining_days_projection, player_names, player_positions, player_ids


def _aggregate_projected_contributions(
    league_key: str,
    roster: Dict[str, List[dict]],
    week_start: date,
    week_end: date,
    stat_meta: Sequence[Dict[str, object]],
    season: str = "2025-26",
    projection_mode: str = "season",
    optimize_roster: bool = False,
) -> Tuple[
    Dict[str, Dict[str, float]],
    Dict[str, str],
    Dict[str, int],
    Dict[str, int],
    Dict[str, dict],
    Dict[str, Dict[str, Dict[str, float]]],
    Dict[str, Dict[str, str]],
    Dict[str, Optional[int]],
]:
    """Calculate projected contributions for each player, including shooting stats and remaining days projection.

    Args:
        league_key: Yahoo league key
        roster: Player roster by date
        week_start: Start date of week
        week_end: End date of week
        stat_meta: Stat category metadata
        season: NBA season string
        projection_mode: One of "season", "last3", "last7", "last7d", "last30d"
        optimize_roster: If True, optimize roster positions for maximum active players

    Returns:
        Tuple of (contributions, player_names, player_total_games, player_remaining_games, player_shooting, remaining_days_projection, player_positions, player_ids)
    """
    stat_ids = [
        str(s.get("stat_id")) for s in stat_meta if s.get("is_only_display_stat") != 1
    ]

    contributions: Dict[str, Dict[str, float]] = {}
    player_names: Dict[str, str] = {}
    player_total_games: Dict[str, int] = {}
    player_remaining_games: Dict[str, int] = {}
    player_shooting: Dict[str, dict] = {}  # Store FGM/FGA, FTM/FTA
    player_ids: Dict[str, Optional[int]] = {}

    # Get today's date for filtering remaining games
    today = date.today()

    # Build mapping of which dates each player was active (on roster AND not benched/IL)
    optimized_positions_by_date: Optional[Dict[str, Dict[str, str]]] = None  # date -> player_key -> position
    if optimize_roster:
        active_dates_map, optimized_positions_by_date = _build_optimized_player_active_dates(league_key, roster, week_start, week_end, season)
    else:
        active_dates_map = _build_player_active_dates(roster)

    # Deduplicate players
    unique_players: Dict[str, dict] = {}
    for players in roster.values():
        for player in players:
            player_key = _player_key(player)
            if player_key and player_key not in unique_players:
                unique_players[player_key] = player

    for player_key, player in unique_players.items():
        player_name = player.get("name", {}).get("full", "")
        player_names[player_key] = player_name

        nba_id = player_fetcher.player_id_lookup(player_name)
        player_ids[player_key] = nba_id
        if not nba_id:
            logger.warning(
                f"Player {player_name} - NBA ID lookup failed, setting contributions to 0"
            )
            contributions[player_key] = {stat_id: 0.0 for stat_id in stat_ids}
            player_total_games[player_key] = 0
            player_remaining_games[player_key] = 0
            player_shooting[player_key] = {}
            continue

        schedule = schedule_fetcher.fetch_player_upcoming_games_from_cache(
            nba_id, week_start.isoformat(), week_end.isoformat(), season
        )

        # Get dates when this player is active (on roster and not benched/IL)
        active_dates = active_dates_map.get(player_key, set())

        # Calculate total games for the entire week (all scheduled games for the team)
        # This represents the total opportunity - how many games the player's team has
        # regardless of whether the player was active on roster for those dates
        # games_played and remaining_games are still filtered by active_dates for contributions
        num_total_games = len(schedule.game_dates) if schedule.game_dates else 0
        player_total_games[player_key] = num_total_games

        # Debug logging for newly added players with no active dates
        if not active_dates and schedule.game_dates:
            logger.warning(
                f"Player {player_name} has {len(schedule.game_dates)} scheduled games but zero active dates. "
                f"Scheduled dates: {schedule.game_dates}. "
                f"This suggests they are benched/IL for all dates OR weren't on the roster."
            )

        # Check if today's game has a boxscore (to avoid double-counting)
        today_str = today.isoformat()
        today_has_boxscore = False
        if today_str in schedule.game_dates and today_str in active_dates:
            # Check if boxscore exists for today by looking at player's games
            player_games_data = boxscore_cache.load_player_games(nba_id, season)
            if player_games_data:
                games_list = player_games_data.get("games", [])
                # Check if any game in the list has today's date
                today_has_boxscore = any(
                    game.get("date") == today_str for game in games_list
                )

        # Filter scheduled games to only include:
        # 1. Dates from today onwards (but exclude today if boxscore exists)
        # 2. Dates where player is in an active roster position
        # This prevents double-counting: if today's game has a boxscore, it's already
        # in current_player_contributions, so we exclude it from remaining projections
        remaining_active_dates = [
            d
            for d in schedule.game_dates
            if d in active_dates
            and ((d > today_str) or (d == today_str and not today_has_boxscore))
        ]
        num_remaining_games = len(remaining_active_dates)
        player_remaining_games[player_key] = num_remaining_games

        # Debug logging for players with games but no remaining games
        if schedule.game_dates and not remaining_active_dates:
            logger.warning(
                f"Player {player_name} has {len(schedule.game_dates)} total games but 0 remaining games. "
                f"Active dates: {sorted(active_dates) if active_dates else 'none'}. "
                f"Schedule dates: {schedule.game_dates}. Today: {today.isoformat()}"
            )

        if not schedule.game_dates:
            contributions[player_key] = {stat_id: 0.0 for stat_id in stat_ids}
            player_shooting[player_key] = {}
            continue

        # Project stats using only remaining active dates
        projected = _project_player_stats(
            league_key,
            player,
            remaining_active_dates,
            stat_meta,
            season,
            projection_mode,
        )
        contributions[player_key] = projected

        # Fetch shooting stats - use appropriate mode
        if projection_mode == "season":
            # Fast path: use pre-computed season stats
            cached_stats = boxscore_cache.load_player_season_stats(nba_id, season)

            if cached_stats:
                # Multiply by remaining active games count to get projected totals
                projected_fgm = cached_stats.get("fgm", 0.0) * num_remaining_games
                projected_fga = cached_stats.get("fga", 0.0) * num_remaining_games
                projected_ftm = cached_stats.get("ftm", 0.0) * num_remaining_games
                projected_fta = cached_stats.get("fta", 0.0) * num_remaining_games

                # Calculate percentages from projected totals, not season averages
                calculated_fg_pct = (
                    projected_fgm / projected_fga if projected_fga > 0 else 0.0
                )
                calculated_ft_pct = (
                    projected_ftm / projected_fta if projected_fta > 0 else 0.0
                )

                player_shooting[player_key] = {
                    "fgm": projected_fgm,
                    "fga": projected_fga,
                    "fg_pct": calculated_fg_pct,
                    "ftm": projected_ftm,
                    "fta": projected_fta,
                    "ft_pct": calculated_ft_pct,
                }

                # Update percentage values in contributions dict to match calculated values
                for stat in stat_meta:
                    stat_id = str(stat.get("stat_id"))
                    stat_name = stat.get("display_name") or stat.get("name") or ""
                    if stat_name == "FG%":
                        contributions[player_key][stat_id] = calculated_fg_pct
                    elif stat_name == "FT%":
                        contributions[player_key][stat_id] = calculated_ft_pct
            else:
                player_shooting[player_key] = {}
        else:
            # Compute shooting stats using the selected mode
            season_start = schedule_fetcher.get_season_start_date(season)
            today = date.today()
            player_stats = compute_player_stats(
                player_id=nba_id,
                mode=projection_mode,
                season_start=season_start,
                today=today,
                agg_mode="avg",
                season=season,
            )

            if player_stats:
                # Calculate projected totals from per-game averages
                projected_fgm = (
                    player_stats.fgm / player_stats.games_count * num_remaining_games
                    if player_stats.games_count > 0
                    else 0.0
                )
                projected_fga = (
                    player_stats.fga / player_stats.games_count * num_remaining_games
                    if player_stats.games_count > 0
                    else 0.0
                )
                projected_ftm = (
                    player_stats.ftm / player_stats.games_count * num_remaining_games
                    if player_stats.games_count > 0
                    else 0.0
                )
                projected_fta = (
                    player_stats.fta / player_stats.games_count * num_remaining_games
                    if player_stats.games_count > 0
                    else 0.0
                )

                # Calculate percentages from projected totals, not season averages
                calculated_fg_pct = (
                    projected_fgm / projected_fga if projected_fga > 0 else 0.0
                )
                calculated_ft_pct = (
                    projected_ftm / projected_fta if projected_fta > 0 else 0.0
                )

                player_shooting[player_key] = {
                    "fgm": projected_fgm,
                    "fga": projected_fga,
                    "fg_pct": calculated_fg_pct,
                    "ftm": projected_ftm,
                    "fta": projected_fta,
                    "ft_pct": calculated_ft_pct,
                }

                # Update percentage values in contributions dict to match calculated values
                for stat in stat_meta:
                    stat_id = str(stat.get("stat_id"))
                    stat_name = stat.get("display_name") or stat.get("name") or ""
                    if stat_name == "FG%":
                        contributions[player_key][stat_id] = calculated_fg_pct
                    elif stat_name == "FT%":
                        contributions[player_key][stat_id] = calculated_ft_pct
            else:
                player_shooting[player_key] = {}

    # Compute daily breakdown
    remaining_days_projection, _, player_positions, _ = (
        _compute_daily_player_contributions(
            league_key, roster, week_start, week_end, stat_meta, season, optimized_positions_by_date
        )
    )

    return (
        contributions,
        player_names,
        player_total_games,
        player_remaining_games,
        player_shooting,
        remaining_days_projection,
        player_positions,
        player_ids,
    )


def _serialize_team_entry(entry: object) -> Optional[dict]:
    team = entry
    if isinstance(entry, dict):
        team = entry.get("team", entry)
    if hasattr(team, "serialized"):
        team = team.serialized()
    if isinstance(team, dict):
        return team
    return None


def _ensure_team_key(team_key: object) -> Optional[str]:
    if isinstance(team_key, bytes):
        return team_key.decode("utf-8")
    if isinstance(team_key, str):
        return team_key
    return None


def _calculate_projected_points(
    stat_meta: Sequence[Dict[str, object]],
    team_a_projection: Dict[str, float],
    team_b_projection: Dict[str, float],
) -> Tuple[Dict[str, float], Dict[str, float]]:
    """Calculate projected team points (wins/losses/ties) based on projections.
    
    For FG% and FT% ties, uses volume (FGA/FTA) as tiebreaker - larger volume wins.
    For other stats, ties count as ties (not 0.5 points each).
    """
    team_a_points = {"win": 0.0, "loss": 0.0, "tie": 0.0}
    team_b_points = {"win": 0.0, "loss": 0.0, "tie": 0.0}

    for stat in stat_meta:
        stat_id = str(stat.get("stat_id"))
        if stat.get("is_only_display_stat") == 1:
            continue

        stat_name = stat.get("display_name") or stat.get("name") or ""
        a_value = team_a_projection.get(stat_id, 0.0)
        b_value = team_b_projection.get(stat_id, 0.0)

        # Determine if lower is better (ascending stat like turnovers)
        is_ascending = stat.get("sort_order") in {"0", 0, "asc"}

        if abs(a_value - b_value) < 0.001:  # Tie (accounting for float precision)
            # For FG% and FT% ties, use volume as tiebreaker
            if stat_name == "FG%":
                a_volume = team_a_projection.get("_FGA", 0.0)
                b_volume = team_b_projection.get("_FGA", 0.0)
                if abs(a_volume - b_volume) > 0.001:
                    # Higher volume wins the tiebreaker
                    if a_volume > b_volume:
                        team_a_points["win"] += 1.0
                        team_b_points["loss"] += 1.0
                    else:
                        team_b_points["win"] += 1.0
                        team_a_points["loss"] += 1.0
                else:
                    # True tie - both volumes equal
                    team_a_points["tie"] += 1.0
                    team_b_points["tie"] += 1.0
            elif stat_name == "FT%":
                a_volume = team_a_projection.get("_FTA", 0.0)
                b_volume = team_b_projection.get("_FTA", 0.0)
                if abs(a_volume - b_volume) > 0.001:
                    # Higher volume wins the tiebreaker
                    if a_volume > b_volume:
                        team_a_points["win"] += 1.0
                        team_b_points["loss"] += 1.0
                    else:
                        team_b_points["win"] += 1.0
                        team_a_points["loss"] += 1.0
                else:
                    # True tie - both volumes equal
                    team_a_points["tie"] += 1.0
                    team_b_points["tie"] += 1.0
            else:
                # Other stats: count as a tie
                team_a_points["tie"] += 1.0
                team_b_points["tie"] += 1.0
        elif (a_value > b_value and not is_ascending) or (
            a_value < b_value and is_ascending
        ):
            # Team A wins
            team_a_points["win"] += 1.0
            team_b_points["loss"] += 1.0
        else:
            # Team B wins
            team_b_points["win"] += 1.0
            team_a_points["loss"] += 1.0

    # Calculate total (wins only, ties don't add to total)
    team_a_points["total"] = team_a_points["win"]
    team_b_points["total"] = team_b_points["win"]

    return team_a_points, team_b_points


def _sum_player_contributions_to_team_total(
    player_contributions: Dict[str, Dict[str, float]],
    player_shooting: Dict[str, dict],
    stat_meta: Sequence[Dict[str, object]],
) -> Dict[str, float]:
    """Sum up individual player contributions to get team totals.

    This properly handles percentage stats by using shooting volume.
    """
    stat_ids = [
        str(s.get("stat_id")) for s in stat_meta if s.get("is_only_display_stat") != 1
    ]

    # Find percentage stat IDs
    percentage_stat_ids = set()
    for stat in stat_meta:
        if stat.get("is_only_display_stat") == 1:
            continue
        stat_name = stat.get("display_name") or stat.get("name") or ""
        if "%" in stat_name:
            percentage_stat_ids.add(str(stat.get("stat_id")))

    # Sum counting stats
    totals = {stat_id: 0.0 for stat_id in stat_ids}
    total_fgm = 0.0
    total_fga = 0.0
    total_ftm = 0.0
    total_fta = 0.0

    for player_key, stats in player_contributions.items():
        shooting = player_shooting.get(player_key, {})
        total_fgm += shooting.get("fgm", 0.0)
        total_fga += shooting.get("fga", 0.0)
        total_ftm += shooting.get("ftm", 0.0)
        total_fta += shooting.get("fta", 0.0)

        for stat_id, value in stats.items():
            if stat_id not in percentage_stat_ids:
                totals[stat_id] += value

    # Calculate percentages from shooting volume
    for stat in stat_meta:
        stat_id = str(stat.get("stat_id"))
        if stat.get("is_only_display_stat") == 1:
            continue
        stat_name = stat.get("display_name") or stat.get("name") or ""

        if stat_name == "FG%":
            totals[stat_id] = (total_fgm / total_fga) if total_fga > 0 else 0.0
        elif stat_name == "FT%":
            totals[stat_id] = (total_ftm / total_fta) if total_fta > 0 else 0.0

    # Add shooting volume as special keys
    totals["_FGM"] = total_fgm
    totals["_FGA"] = total_fga
    totals["_FTM"] = total_ftm
    totals["_FTA"] = total_fta

    return totals


def _build_matchup_projection(
    league_key: str,
    stat_meta: Sequence[Dict[str, object]],
    week_start: date,
    week_end: date,
    team_entries: Sequence[dict],
    roster_cache: Optional[Dict[str, Dict[str, List[dict]]]] = None,
    week: Optional[int] = None,
    season: str = "2025-26",
    projection_mode: str = "season",
    optimize_map: Optional[Dict[str, bool]] = None,
) -> Dict[str, object]:
    """Build matchup projection for teams.

    Args:
        league_key: Yahoo league key
        stat_meta: Stat category metadata
        week_start: Start date of week
        week_end: End date of week
        team_entries: List of team data dicts
        roster_cache: Cache of rosters by team
        week: Week number
        season: NBA season string
        projection_mode: One of "season", "last3", "last7", "last7d", "last30d"
        optimize_map: Dict mapping team_key to whether to optimize that team's roster

    Returns:
        Dict with matchup projection data
    """
    roster_cache = roster_cache or {}
    optimize_map = optimize_map or {}

    projected_teams = []
    for team_data in team_entries:
        team_key_value = _ensure_team_key(team_data.get("team_key"))
        if not team_key_value:
            continue
        team_id = extract_team_id(team_key_value)
        roster = roster_cache.get(team_key_value)
        if roster is None:
            roster = _collect_roster(league_key, team_id, week_start, week_end)
            roster_cache[team_key_value] = roster

        # Check if this team should use optimized roster positions
        optimize_roster = optimize_map.get(team_key_value, False)

        projection = _project_team(
            league_key, roster, week_start, week_end, stat_meta, season, projection_mode, optimize_roster
        )

        # Get team points from Yahoo
        if week is not None:
            weekly: Dict[str, Dict[str, float]] = {}
            try:
                weekly = fetch_team_stats_for_week(league_key, team_id, week)
            except Exception:  # noqa: BLE001
                # Catch all exceptions (auth errors, server errors, etc.)
                # Fall back to stats from team_data
                weekly = {}
            team_points = weekly.get("team_points", _extract_team_points(team_data))
        else:
            team_points = _extract_team_points(team_data)

        raw_name = team_data.get("name")
        if isinstance(raw_name, dict):
            team_name = raw_name.get("full") or raw_name.get("name")
        else:
            team_name = raw_name
        if isinstance(team_name, bytes):
            team_name = team_name.decode("utf-8", errors="ignore")
        if not isinstance(team_name, str):
            team_name = str(team_name)

        # Get projected contributions per player
        (
            proj_contributions,
            proj_player_names,
            player_total_games,
            player_remaining_games,
            proj_player_shooting,
            remaining_days_projection,
            player_positions,
            proj_player_ids,
        ) = _aggregate_projected_contributions(
            league_key, roster, week_start, week_end, stat_meta, season, projection_mode, optimize_roster
        )

        # Get actual current week contributions for player breakdown
        (
            current_contributions,
            current_player_names,
            current_player_shooting,
            is_on_roster_today,
            player_games_played,
            current_player_ids,
        ) = _aggregate_current_week_player_contributions(
            league_key, roster, week_start, week_end, stat_meta, season, optimize_roster
        )

        # Calculate team current totals by summing up player contributions
        # This is more accurate than Yahoo stats minus inactive contributions
        current_team_total = _sum_player_contributions_to_team_total(
            current_contributions, current_player_shooting, stat_meta
        )

        projected_teams.append(
            {
                "team_key": team_key_value,
                "team_name": team_name,
                "projection": projection,
                "current": current_team_total,  # Sum of active player contributions
                "team_points": team_points,
                "current_player_contributions": current_contributions,  # Actual stats accumulated so far this week
                "current_player_names": current_player_names,
                "current_player_shooting": current_player_shooting,  # Actual shooting stats from games played
                "current_player_ids": current_player_ids,  # NBA player IDs for current contributions
                "player_contributions": proj_contributions,  # Projected remaining contributions
                "player_names": proj_player_names,
                "player_total_games": player_total_games,
                "player_remaining_games": player_remaining_games,
                "player_games_played": player_games_played,  # Games played so far this week in active roster spot
                "player_shooting": proj_player_shooting,  # Projected shooting stats for remaining games
                "player_ids": proj_player_ids,  # NBA player IDs for projections
                "is_on_roster_today": is_on_roster_today,  # Track which players are still on roster
                "remaining_days_projection": remaining_days_projection,
                "player_positions": player_positions,  # Track player positions by date
            }
        )

    # Calculate projected points for head-to-head matchups
    if len(projected_teams) == 2:
        proj_points_a, proj_points_b = _calculate_projected_points(
            stat_meta,
            projected_teams[0]["projection"],
            projected_teams[1]["projection"],
        )
        projected_teams[0]["projected_team_points"] = proj_points_a
        projected_teams[1]["projected_team_points"] = proj_points_b

    return {
        "stat_categories": stat_meta,
        "teams": projected_teams,
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
    }


def _resolve_matchup_teams(matchup: object) -> Tuple[dict, dict]:
    teams: List[dict] = []
    teams_iterable = getattr(matchup, "teams", [])
    for entry in teams_iterable:
        team_dict = _serialize_team_entry(entry)
        if not team_dict:
            continue
        teams.append(team_dict)
    if len(teams) != 2:
        raise ValueError("Unexpected matchup team count")
    return teams[0], teams[1]


def project_matchup(
    league_key: str,
    team_key: str,
    week: Optional[int] = None,
    projection_mode: str = "season",
    optimize_user_roster: bool = False,
    optimize_opponent_roster: bool = False,
) -> Dict[str, object]:
    """Project matchup statistics for a team.

    Args:
        league_key: Yahoo league key
        team_key: Yahoo team key
        week: Week number (defaults to current week)
        projection_mode: One of "season", "last3", "last7", "last7d", "last30d"
        optimize_user_roster: If True, optimize user's roster positions for maximum active players
        optimize_opponent_roster: If True, optimize opponent's roster positions for maximum active players

    Returns:
        Dict with projection data
    """
    # Determine season from date first, then load season-specific metadata.
    # Loading the global metadata (no season arg) is unreliable: the global
    # metadata.json is legacy/stale — all refresh operations write to
    # season-specific files (metadata_2025-26.json).
    season = _current_season()
    metadata = boxscore_cache.load_metadata(season)
    games_cached = metadata.get("games_cached", 0)

    if games_cached == 0:
        raise ValueError(
            "Box score cache is empty. Please run /refresh first to build the cache."
        )

    # Check if season stats have been computed
    stats_dir = boxscore_cache.get_cache_dir() / "season_stats" / season
    if not stats_dir.exists() or not any(stats_dir.glob("*.json")):
        raise ValueError(
            f"Season statistics not computed for {season}. Please run /refresh to compute player stats."
        )

    matchup, _ = fetch_matchup_context(league_key, team_key, week=week)
    week_start = date.fromisoformat(matchup.week_start)
    week_end = date.fromisoformat(matchup.week_end)
    week_value = getattr(matchup, "week", None)

    team_a, team_b = _resolve_matchup_teams(matchup)
    stat_meta = fetch_league_stat_categories(league_key)
    
    # Build optimization map - determine which teams need optimization
    optimize_map: Dict[str, bool] = {}
    if team_a.get("team_key") == team_key:
        optimize_map[team_key] = optimize_user_roster
        optimize_map[team_b.get("team_key")] = optimize_opponent_roster
    else:
        optimize_map[team_key] = optimize_user_roster
        optimize_map[team_a.get("team_key")] = optimize_opponent_roster
    
    projection_bundle = _build_matchup_projection(
        league_key,
        stat_meta,
        week_start,
        week_end,
        [team_a, team_b],
        week=week_value,
        season=season,
        projection_mode=projection_mode,
        optimize_map=optimize_map,
    )

    teams = projection_bundle["teams"]
    user_entry = next(
        (team for team in teams if team.get("team_key") == team_key), None
    )
    if user_entry is None:
        raise ValueError("User team not found in matchup data")

    opponent_entry = next((team for team in teams if team is not user_entry), None)

    return {
        "stat_categories": projection_bundle["stat_categories"],
        "user_projection": user_entry.get("projection", {}),
        "opponent_projection": (opponent_entry or {}).get("projection", {}),
        "user_current": user_entry.get("current", {}),
        "opponent_current": (opponent_entry or {}).get("current", {}),
        "user_team_points": user_entry.get("team_points", {}),
        "opponent_team_points": (opponent_entry or {}).get("team_points", {}),
        "user_projected_team_points": user_entry.get("projected_team_points", {}),
        "opponent_projected_team_points": (opponent_entry or {}).get(
            "projected_team_points", {}
        ),
        "current_player_contributions": user_entry.get(
            "current_player_contributions", {}
        ),
        "current_player_names": user_entry.get("current_player_names", {}),
        "current_player_shooting": user_entry.get("current_player_shooting", {}),
        "current_player_ids": user_entry.get("current_player_ids", {}),
        "player_contributions": user_entry.get("player_contributions", {}),
        "player_names": user_entry.get("player_names", {}),
        "player_ids": user_entry.get("player_ids", {}),
        "player_total_games": user_entry.get("player_total_games", {}),
        "player_remaining_games": user_entry.get("player_remaining_games", {}),
        "player_games_played": user_entry.get("player_games_played", {}),
        "player_shooting": user_entry.get("player_shooting", {}),
        "is_on_roster_today": user_entry.get("is_on_roster_today", {}),
        "opponent_current_player_contributions": (opponent_entry or {}).get(
            "current_player_contributions", {}
        ),
        "opponent_current_player_names": (opponent_entry or {}).get(
            "current_player_names", {}
        ),
        "opponent_current_player_shooting": (opponent_entry or {}).get(
            "current_player_shooting", {}
        ),
        "opponent_current_player_ids": (opponent_entry or {}).get(
            "current_player_ids", {}
        ),
        "opponent_player_contributions": (opponent_entry or {}).get(
            "player_contributions", {}
        ),
        "opponent_player_names": (opponent_entry or {}).get("player_names", {}),
        "opponent_player_ids": (opponent_entry or {}).get("player_ids", {}),
        "opponent_player_total_games": (opponent_entry or {}).get(
            "player_total_games", {}
        ),
        "opponent_player_remaining_games": (opponent_entry or {}).get(
            "player_remaining_games", {}
        ),
        "opponent_player_games_played": (opponent_entry or {}).get(
            "player_games_played", {}
        ),
        "opponent_player_shooting": (opponent_entry or {}).get("player_shooting", {}),
        "opponent_is_on_roster_today": (opponent_entry or {}).get(
            "is_on_roster_today", {}
        ),
        "remaining_days_projection": user_entry.get("remaining_days_projection", {}),
        "player_positions": user_entry.get("player_positions", {}),
        "opponent_remaining_days_projection": (opponent_entry or {}).get(
            "remaining_days_projection", {}
        ),
        "opponent_player_positions": (opponent_entry or {}).get("player_positions", {}),
        "week": getattr(matchup, "week", None),
        "week_start": projection_bundle["week_start"],
        "week_end": projection_bundle["week_end"],
        "opponent_team": opponent_entry,
        "user_team": user_entry,
    }


def project_league_matchups(
    league_key: str,
    *,
    anchor_team_key: Optional[str] = None,
    projection_mode: str = "season",
    summary_only: bool = False,
) -> Dict[str, object]:
    """Project all matchups in a league.

    Args:
        league_key: Yahoo league key
        anchor_team_key: Team key to use for determining current week
        projection_mode: One of "season", "last3", "last7", "last7d", "last30d"
        summary_only: If True, only return summary data (team names/scores) without detailed projections

    Returns:
        Dict with all matchup projections
    """
    # Only check cache if we're doing detailed projections
    if not summary_only:
        # Determine season from date first, then load season-specific metadata.
        season = _current_season()
        metadata = boxscore_cache.load_metadata(season)
        games_cached = metadata.get("games_cached", 0)

        if games_cached == 0:
            raise ValueError(
                "Box score cache is empty. Please run /refresh first to build the cache."
            )

        # Check if season stats have been computed
        stats_dir = boxscore_cache.get_cache_dir() / "season_stats" / season
        if not stats_dir.exists() or not any(stats_dir.glob("*.json")):
            raise ValueError(
                f"Season statistics not computed for {season}. Please run /refresh to compute player stats."
            )
    else:
        # For summary only, we don't need cache data
        season = _current_season()

    if anchor_team_key is None:
        anchor_team_key = fetch_user_team_key(league_key)
    anchor_team_id = extract_team_id(anchor_team_key)
    current_week = determine_current_week(league_key, anchor_team_id)

    scoreboard = fetch_league_scoreboard(league_key, current_week)
    stat_meta = fetch_league_stat_categories(league_key)
    roster_cache: Dict[str, Dict[str, List[dict]]] = {}

    # Get league name from scoreboard
    league_name = ""
    if hasattr(scoreboard, "league"):
        league = scoreboard.league
        if hasattr(league, "name"):
            league_name = league.name
        elif isinstance(league, dict):
            league_name = league.get("name", "")

    projections: List[Dict[str, object]] = []
    matchups_iter = scoreboard.matchups if hasattr(scoreboard, "matchups") else []
    for matchup_entry in matchups_iter:
        matchup = (
            matchup_entry.get("matchup")
            if isinstance(matchup_entry, dict)
            else matchup_entry
        )
        if not matchup:
            continue
        try:
            team_a, team_b = _resolve_matchup_teams(matchup)
        except ValueError:
            continue

        week_value = getattr(matchup, "week", None)
        week_start = date.fromisoformat(getattr(matchup, "week_start"))
        week_end = date.fromisoformat(getattr(matchup, "week_end"))

        if summary_only:
            # For summary mode, just extract basic team info without expensive calculations
            # Extract total points from team_points dict
            team_a_points = team_a.get("team_points", {})
            if isinstance(team_a_points, dict):
                team_a_total = float(team_a_points.get("total", 0))
            else:
                team_a_total = 0.0

            team_b_points = team_b.get("team_points", {})
            if isinstance(team_b_points, dict):
                team_b_total = float(team_b_points.get("total", 0))
            else:
                team_b_total = 0.0

            # Extract projected points
            team_a_projected = team_a.get("team_projected_points", {})
            if isinstance(team_a_projected, dict):
                team_a_proj_total = float(team_a_projected.get("total", 0))
            else:
                team_a_proj_total = 0.0

            team_b_projected = team_b.get("team_projected_points", {})
            if isinstance(team_b_projected, dict):
                team_b_proj_total = float(team_b_projected.get("total", 0))
            else:
                team_b_proj_total = 0.0

            bundle = {
                "week": week_value,
                "week_start": week_start.isoformat(),
                "week_end": week_end.isoformat(),
                "teams": [
                    {
                        "team_name": team_a.get("name", ""),
                        "team_key": team_a.get("team_key", ""),
                        "team_points": team_a_total,
                        "projected_team_points": team_a_proj_total,
                    },
                    {
                        "team_name": team_b.get("name", ""),
                        "team_key": team_b.get("team_key", ""),
                        "team_points": team_b_total,
                        "projected_team_points": team_b_proj_total,
                    },
                ],
                "stat_categories": stat_meta,
            }
        else:
            # Full detailed projection with roster collection
            bundle = _build_matchup_projection(
                league_key,
                stat_meta,
                week_start,
                week_end,
                [team_a, team_b],
                roster_cache,
                week=week_value,
                season=season,
                projection_mode=projection_mode,
            )
            bundle["week"] = getattr(matchup, "week", None)

        projections.append(bundle)

    return {
        "league_name": league_name,
        "week": getattr(scoreboard, "week", current_week),
        "stat_categories": stat_meta,
        "matchups": projections,
    }
