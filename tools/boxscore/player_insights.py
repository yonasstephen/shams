"""Player performance insights using play-by-play data.

This module fetches NBA play-by-play data on-demand and analyzes it to provide
insights about a player's performance in a specific game.
"""

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from tools.utils import nba_api_config  # noqa: F401 - Configure NBA API timeout


@dataclass
class FoulEventData:
    """Data for a single foul event."""

    quarter: int
    time_remaining: str
    foul_number: int
    foul_type: str
    elapsed_minutes: float


@dataclass
class SubstitutionEventData:
    """Data for a substitution event."""

    quarter: int
    time_remaining: str
    event_type: str  # "in" or "out"
    elapsed_minutes: float


@dataclass
class QuarterBreakdownData:
    """Stats breakdown for a single quarter."""

    quarter: int
    quarter_label: str
    minutes: float
    points: int
    fouls: int
    field_goals_made: int
    field_goals_attempted: int
    three_pointers_made: int
    three_pointers_attempted: int
    free_throws_made: int
    free_throws_attempted: int
    rebounds: int
    assists: int
    steals: int
    blocks: int
    turnovers: int


@dataclass
class InsightData:
    """Individual insight about player performance."""

    type: str
    severity: str
    message: str
    details: Optional[Dict[str, Any]] = None


@dataclass
class PlayerInsightsData:
    """Complete insights data for a player in a game."""

    player_id: int
    player_name: str
    game_id: str
    total_minutes: float
    insights: List[InsightData]
    quarter_breakdown: List[QuarterBreakdownData]
    foul_timeline: List[FoulEventData]
    substitution_timeline: List[SubstitutionEventData]


def fetch_play_by_play(game_id: str) -> Optional[List[Dict[str, Any]]]:
    """Fetch play-by-play data for a game using V3 API.

    Args:
        game_id: NBA game ID (e.g., "0022500671")

    Returns:
        List of play-by-play events or None if unavailable
    """
    try:
        from nba_api.stats.endpoints import playbyplayv3

        pbp = playbyplayv3.PlayByPlayV3(game_id=game_id)
        df = pbp.get_data_frames()[0]

        if df.empty:
            return None

        return df.to_dict("records")
    except Exception as e:
        print(f"Error fetching play-by-play for game {game_id}: {e}")
        return None


def _parse_clock_string(clock_str: str) -> str:
    """Parse V3 clock string (PT12M00.00S) to MM:SS format.

    Args:
        clock_str: Clock in V3 format like "PT12M00.00S"

    Returns:
        Time in "MM:SS" format
    """
    if not clock_str:
        return "0:00"

    # Parse format like "PT12M00.00S" or "PT09M30.00S"
    match = re.match(r'PT(\d+)M(\d+(?:\.\d+)?)S', clock_str)
    if match:
        minutes = int(match.group(1))
        seconds = int(float(match.group(2)))
        return f"{minutes}:{seconds:02d}"

    return "0:00"


def _parse_time_to_seconds(time_str: str) -> float:
    """Parse MM:SS time string to total seconds.

    Args:
        time_str: Time in "MM:SS" format

    Returns:
        Total seconds
    """
    try:
        parts = time_str.split(":")
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
    except (ValueError, AttributeError):
        pass
    return 0


def _calculate_elapsed_minutes(quarter: int, time_remaining: str) -> float:
    """Calculate total elapsed minutes in the game.

    Args:
        quarter: Quarter number (1-4 for regulation, 5+ for OT)
        time_remaining: Time remaining in quarter (e.g., "10:30")

    Returns:
        Total elapsed minutes from game start
    """
    seconds_remaining = _parse_time_to_seconds(time_remaining)

    # Regulation quarters are 12 minutes, OT is 5 minutes
    if quarter <= 4:
        quarter_length = 12 * 60  # seconds
        completed_quarters = quarter - 1
        completed_seconds = completed_quarters * 12 * 60
    else:
        # OT periods
        completed_seconds = 48 * 60 + (quarter - 5) * 5 * 60
        quarter_length = 5 * 60

    # Time played in current quarter
    time_played_in_quarter = quarter_length - seconds_remaining

    return (completed_seconds + time_played_in_quarter) / 60


def _get_quarter_label(quarter: int) -> str:
    """Get human-readable quarter label.

    Args:
        quarter: Quarter number

    Returns:
        Label like "Q1", "Q2", "OT1", etc.
    """
    if quarter <= 4:
        return f"Q{quarter}"
    return f"OT{quarter - 4}"


def _extract_foul_type(description: str) -> str:
    """Extract foul type from description.

    Args:
        description: Event description like "Tyson P.FOUL (P1.T1)"

    Returns:
        Foul type string
    """
    description_upper = description.upper()

    if "OFF.FOUL" in description_upper or "OFFENSIVE" in description_upper:
        return "offensive"
    if "T.FOUL" in description_upper or "TECHNICAL" in description_upper:
        return "technical"
    if "FLAGRANT" in description_upper:
        return "flagrant"
    if "S.FOUL" in description_upper or "SHOOTING" in description_upper:
        return "shooting"
    if "L.B.FOUL" in description_upper or "LOOSE BALL" in description_upper:
        return "loose_ball"

    return "personal"


def _extract_foul_events(
    pbp_events: List[Dict[str, Any]], player_id: int
) -> List[FoulEventData]:
    """Extract foul events for a specific player.

    Args:
        pbp_events: List of play-by-play events (V3 format)
        player_id: NBA player ID

    Returns:
        List of foul events
    """
    fouls = []
    foul_count = 0

    for event in pbp_events:
        action_type = event.get("actionType", "")
        person_id = event.get("personId")

        # Check if this is a foul event involving our player
        if action_type == "Foul" and person_id == player_id:
            foul_count += 1
            quarter = event.get("period", 1)
            clock = event.get("clock", "PT0M0.00S")
            time_remaining = _parse_clock_string(clock)
            description = event.get("description", "")

            fouls.append(
                FoulEventData(
                    quarter=quarter,
                    time_remaining=time_remaining,
                    foul_number=foul_count,
                    foul_type=_extract_foul_type(description),
                    elapsed_minutes=_calculate_elapsed_minutes(quarter, time_remaining),
                )
            )

    return fouls


def _extract_substitution_events(
    pbp_events: List[Dict[str, Any]], player_id: int, player_name: str
) -> List[SubstitutionEventData]:
    """Extract substitution events for a specific player.

    Args:
        pbp_events: List of play-by-play events (V3 format)
        player_id: NBA player ID
        player_name: Player name to match in descriptions

    Returns:
        List of substitution events
    """
    subs = []

    # Build name variations for matching
    # Names might appear as "Doncic", "L. Doncic", "Luka Doncic"
    name_parts = player_name.split()
    last_name = name_parts[-1] if name_parts else player_name
    # Remove accents for matching (e.g., "Dončić" -> "Doncic")
    last_name_normalized = last_name.replace("č", "c").replace("ć", "c")

    for event in pbp_events:
        action_type = event.get("actionType", "")

        if action_type == "Substitution":
            quarter = event.get("period", 1)
            clock = event.get("clock", "PT0M0.00S")
            time_remaining = _parse_clock_string(clock)
            elapsed = _calculate_elapsed_minutes(quarter, time_remaining)
            description = event.get("description", "")
            person_id = event.get("personId")

            # V3 format: "SUB: X FOR Y"
            # - personId is the player LEAVING (being replaced)
            # - X (after "SUB:") is the player ENTERING
            # - Y (after "FOR") is the player LEAVING

            # Player leaving (personId matches = they're being replaced)
            if person_id == player_id:
                subs.append(
                    SubstitutionEventData(
                        quarter=quarter,
                        time_remaining=time_remaining,
                        event_type="out",
                        elapsed_minutes=elapsed,
                    )
                )
            # Player entering - check description for "SUB: <player_name>"
            else:
                # Check if player is entering (appears after "SUB:" in description)
                desc_upper = description.upper()
                if f"SUB: {last_name.upper()}" in desc_upper or f"SUB: {last_name_normalized.upper()}" in desc_upper:
                    subs.append(
                        SubstitutionEventData(
                            quarter=quarter,
                            time_remaining=time_remaining,
                            event_type="in",
                            elapsed_minutes=elapsed,
                        )
                    )

    return subs


def _calculate_quarter_breakdown(
    pbp_events: List[Dict[str, Any]],
    player_id: int,
    substitutions: List[SubstitutionEventData],
) -> List[QuarterBreakdownData]:
    """Calculate stats breakdown by quarter.

    Args:
        pbp_events: List of play-by-play events (V3 format)
        player_id: NBA player ID
        substitutions: Pre-calculated substitution events

    Returns:
        List of quarter breakdown stats
    """
    # Find all quarters that have events
    quarters = set()
    for event in pbp_events:
        quarters.add(event.get("period", 1))

    # Determine which quarters the player started
    # Player starts Q1 if their first sub is "out" (they were already on court)
    # Player starts Qn (n>1) if they ended previous quarter on court
    started_quarters = set()

    # Check Q1: if first sub for player in Q1 is "out", they started
    q1_subs = [s for s in substitutions if s.quarter == 1]
    if q1_subs:
        # Sort by time remaining descending (chronological)
        first_sub = max(q1_subs, key=lambda s: _parse_time_to_seconds(s.time_remaining))
        if first_sub.event_type == "out":
            started_quarters.add(1)
    else:
        # No subs in Q1 - check if player had any events in Q1
        q1_player_events = [
            e for e in pbp_events
            if e.get("period") == 1 and e.get("personId") == player_id
        ]
        if q1_player_events:
            started_quarters.add(1)

    # For subsequent quarters, track if player was on court at end of previous quarter
    on_court_at_end = 1 in started_quarters
    for q in sorted(quarters):
        if q == 1:
            continue

        q_subs = [s for s in substitutions if s.quarter == q - 1]
        if q_subs:
            # Find the last sub in previous quarter
            last_sub = min(q_subs, key=lambda s: _parse_time_to_seconds(s.time_remaining))
            on_court_at_end = last_sub.event_type == "in"
        # If no subs in previous quarter, maintain previous on_court status

        if on_court_at_end:
            started_quarters.add(q)

        # Update on_court_at_end for this quarter
        q_subs_current = [s for s in substitutions if s.quarter == q]
        if q_subs_current:
            last_sub = min(q_subs_current, key=lambda s: _parse_time_to_seconds(s.time_remaining))
            on_court_at_end = last_sub.event_type == "in"
        # If no subs in this quarter, maintain previous on_court status based on started

    breakdown = []

    for quarter in sorted(quarters):
        quarter_events = [e for e in pbp_events if e.get("period") == quarter]

        # Calculate stats for this quarter
        points = 0
        fouls = 0
        fgm = 0
        fga = 0
        fg3m = 0
        fg3a = 0
        ftm = 0
        fta = 0
        rebounds = 0
        assists = 0
        steals = 0
        blocks = 0
        turnovers = 0

        for event in quarter_events:
            action_type = event.get("actionType", "")
            person_id = event.get("personId")
            description = event.get("description", "")

            # Made shot - check if our player made it or assisted
            if action_type == "Made Shot":
                shot_value = event.get("shotValue", 2)
                if person_id == player_id:
                    points += shot_value
                    fgm += 1
                    fga += 1
                    if shot_value == 3:
                        fg3m += 1
                        fg3a += 1
                # Check for assist - player name appears in description after "AST"
                elif "AST" in description.upper():
                    # V3 API doesn't have separate assist field, check description
                    # Format: "Doncic 3' Shot (10 PTS) (Ayton 1 AST)"
                    pass  # Assists are tracked separately below

            # Missed shot
            elif action_type == "Missed Shot":
                if person_id == player_id:
                    is_field_goal = event.get("isFieldGoal", 1)
                    if is_field_goal:
                        fga += 1
                        # Check if it was a 3-pointer from description
                        if "3PT" in description.upper():
                            fg3a += 1

            # Free throw
            elif action_type == "Free Throw":
                if person_id == player_id:
                    fta += 1
                    shot_result = event.get("shotResult", "")
                    if shot_result == "Made":
                        ftm += 1
                        points += 1

            # Foul
            elif action_type == "Foul":
                if person_id == player_id:
                    fouls += 1

            # Rebound
            elif action_type == "Rebound":
                if person_id == player_id:
                    rebounds += 1

            # Turnover
            elif action_type == "Turnover":
                if person_id == player_id:
                    turnovers += 1

            # Steal - person_id is the player who got the steal
            elif action_type == "Steal":
                if person_id == player_id:
                    steals += 1

            # Block - person_id is the player who got the block
            elif action_type == "Block":
                if person_id == player_id:
                    blocks += 1

        # Count assists from made shots where our player is mentioned in AST
        # V3 format: description contains "(PlayerName N AST)"
        for event in quarter_events:
            if event.get("actionType") == "Made Shot":
                description = event.get("description", "")
                # Look for assist pattern in description
                if " AST)" in description.upper():
                    # Extract the name before AST and check if it matches
                    # Format: "... (Doncic 1 AST)"
                    import re
                    ast_match = re.search(r'\(([^)]+)\s+\d+\s+AST\)', description, re.IGNORECASE)
                    if ast_match:
                        assister_name = ast_match.group(1).strip()
                        # Check all events to find player name
                        for e in pbp_events:
                            if e.get("personId") == player_id:
                                player_name_in_event = e.get("playerNameI", "") or e.get("playerName", "")
                                # Check if the assister name matches our player
                                if player_name_in_event and (
                                    assister_name.upper() in player_name_in_event.upper() or
                                    player_name_in_event.upper() in assister_name.upper()
                                ):
                                    assists += 1
                                    break

        # Calculate minutes in this quarter
        quarter_subs = [s for s in substitutions if s.quarter == quarter]
        started_quarter = quarter in started_quarters
        # Check if player had any events in this quarter
        had_events = any(
            e.get("personId") == player_id
            for e in quarter_events
        )
        minutes = _estimate_quarter_minutes(quarter, quarter_subs, started_quarter, had_events)

        breakdown.append(
            QuarterBreakdownData(
                quarter=quarter,
                quarter_label=_get_quarter_label(quarter),
                minutes=minutes,
                points=points,
                fouls=fouls,
                field_goals_made=fgm,
                field_goals_attempted=fga,
                three_pointers_made=fg3m,
                three_pointers_attempted=fg3a,
                free_throws_made=ftm,
                free_throws_attempted=fta,
                rebounds=rebounds,
                assists=assists,
                steals=steals,
                blocks=blocks,
                turnovers=turnovers,
            )
        )

    return breakdown


def _estimate_quarter_minutes(
    quarter: int,
    quarter_subs: List[SubstitutionEventData],
    started_quarter: bool = False,
    had_events: bool = False,
) -> float:
    """Estimate minutes played in a quarter based on substitutions.

    This is an approximation since we track sub in/out events.

    Args:
        quarter: Quarter number
        quarter_subs: Substitution events for this quarter
        started_quarter: Whether the player started the quarter on court
        had_events: Whether the player had any events in this quarter

    Returns:
        Estimated minutes played
    """
    quarter_length = 12.0 if quarter <= 4 else 5.0
    quarter_seconds = quarter_length * 60

    if not quarter_subs:
        # No substitutions in this quarter
        if not had_events:
            # No subs and no events = didn't play
            return 0.0
        # Had events but no subs = played the whole quarter if started
        return quarter_length if started_quarter else 0.0

    minutes = 0.0
    is_on_court = started_quarter
    last_time = quarter_seconds  # Start of quarter in seconds

    # Sort by time remaining (descending = chronological order)
    sorted_subs = sorted(quarter_subs, key=lambda s: -_parse_time_to_seconds(s.time_remaining))

    for sub in sorted_subs:
        current_seconds = _parse_time_to_seconds(sub.time_remaining)

        if sub.event_type == "in":
            is_on_court = True
            last_time = current_seconds
        elif sub.event_type == "out":
            if is_on_court:
                minutes += (last_time - current_seconds) / 60
            is_on_court = False
            last_time = current_seconds

    # If still on court at end of quarter, add remaining time
    if is_on_court:
        minutes += last_time / 60

    return max(0.0, min(minutes, quarter_length))


def _detect_foul_trouble(fouls: List[FoulEventData]) -> List[InsightData]:
    """Detect foul trouble patterns.

    Args:
        fouls: List of foul events

    Returns:
        List of foul-related insights
    """
    insights = []

    if not fouls:
        return insights

    # Check for early foul trouble (2+ fouls in first quarter)
    first_quarter_fouls = [f for f in fouls if f.quarter == 1]
    if len(first_quarter_fouls) >= 2:
        insights.append(
            InsightData(
                type="foul_trouble",
                severity="warning",
                message=f"Early foul trouble: {len(first_quarter_fouls)} fouls in Q1",
                details={
                    "fouls_in_q1": len(first_quarter_fouls),
                    "foul_times": [f.time_remaining for f in first_quarter_fouls],
                },
            )
        )

    # Check for quick fouls (3+ fouls in first 10 minutes)
    early_fouls = [f for f in fouls if f.elapsed_minutes <= 10]
    if len(early_fouls) >= 3:
        insights.append(
            InsightData(
                type="foul_trouble",
                severity="critical",
                message=f"Severe foul trouble: {len(early_fouls)} fouls in first 10 minutes",
                details={
                    "fouls_in_first_10_min": len(early_fouls),
                    "times": [
                        f"{f.elapsed_minutes:.1f} min" for f in early_fouls
                    ],
                },
            )
        )

    # Check for first-half foul trouble (4+ fouls by halftime)
    first_half_fouls = [f for f in fouls if f.quarter <= 2]
    if len(first_half_fouls) >= 4:
        insights.append(
            InsightData(
                type="foul_trouble",
                severity="critical",
                message=f"4+ fouls by halftime ({len(first_half_fouls)} total)",
                details={
                    "first_half_fouls": len(first_half_fouls),
                },
            )
        )

    # Check for fouling out risk (5 fouls before 4th quarter)
    pre_fourth_fouls = [f for f in fouls if f.quarter < 4]
    if len(pre_fourth_fouls) >= 5:
        insights.append(
            InsightData(
                type="foul_trouble",
                severity="critical",
                message="Foul out risk: 5 fouls before Q4",
                details={"fouls_before_q4": len(pre_fourth_fouls)},
            )
        )

    return insights


def _detect_minutes_patterns(
    total_minutes: float,
    quarter_breakdown: List[QuarterBreakdownData],
    substitutions: List[SubstitutionEventData],
) -> List[InsightData]:
    """Detect unusual minutes patterns.

    Args:
        total_minutes: Total minutes played
        quarter_breakdown: Stats by quarter
        substitutions: Substitution events

    Returns:
        List of minutes-related insights
    """
    insights = []

    # Check for very low minutes
    if total_minutes < 15 and total_minutes > 0:
        insights.append(
            InsightData(
                type="limited_minutes",
                severity="warning",
                message=f"Limited playing time: {total_minutes:.1f} minutes",
                details={"total_minutes": total_minutes},
            )
        )

    # Check for benched entire quarter (after playing in previous quarter)
    for i, q in enumerate(quarter_breakdown):
        if q.minutes == 0 and q.quarter > 1 and i > 0:
            # Check if player played in previous quarter
            prev_q = quarter_breakdown[i - 1]
            if prev_q.minutes > 0:
                insights.append(
                    InsightData(
                        type="benched",
                        severity="info",
                        message=f"Did not play in {q.quarter_label}",
                        details={"quarter": q.quarter_label},
                    )
                )

    return insights


def _get_player_name_from_events(
    pbp_events: List[Dict[str, Any]], player_id: int
) -> str:
    """Extract player name from play-by-play events.

    Args:
        pbp_events: List of play-by-play events (V3 format)
        player_id: NBA player ID

    Returns:
        Player name or "Unknown"
    """
    for event in pbp_events:
        if event.get("personId") == player_id:
            name = event.get("playerName") or event.get("playerNameI")
            if name:
                return name
    return "Unknown"


def analyze_player_performance(
    game_id: str, player_id: int, player_name: Optional[str] = None
) -> Optional[PlayerInsightsData]:
    """Analyze a player's performance in a game using play-by-play data.

    Args:
        game_id: NBA game ID
        player_id: NBA player ID
        player_name: Optional player name (will be extracted from PBP if not provided)

    Returns:
        PlayerInsightsData object or None if data unavailable
    """
    # Fetch play-by-play data
    pbp_events = fetch_play_by_play(game_id)

    if not pbp_events:
        return None

    # Get player name if not provided
    if not player_name:
        player_name = _get_player_name_from_events(pbp_events, player_id)

    # Extract events for this player
    fouls = _extract_foul_events(pbp_events, player_id)
    substitutions = _extract_substitution_events(pbp_events, player_id, player_name)
    quarter_breakdown = _calculate_quarter_breakdown(pbp_events, player_id, substitutions)

    # Calculate total minutes
    total_minutes = sum(q.minutes for q in quarter_breakdown)

    # Generate insights
    insights = []
    insights.extend(_detect_foul_trouble(fouls))
    insights.extend(_detect_minutes_patterns(total_minutes, quarter_breakdown, substitutions))

    return PlayerInsightsData(
        player_id=player_id,
        player_name=player_name,
        game_id=game_id,
        total_minutes=total_minutes,
        insights=insights,
        quarter_breakdown=quarter_breakdown,
        foul_timeline=fouls,
        substitution_timeline=substitutions,
    )
