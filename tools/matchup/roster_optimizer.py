"""Roster optimization algorithm for maximizing active players."""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


def _get_eligible_slots_for_position(player_positions: List[str], slot_position: str) -> bool:
    """Check if a player with given positions can fill a specific slot.

    Args:
        player_positions: List of player's eligible positions (e.g., ["PG", "SG"])
        slot_position: The roster slot position (e.g., "PG", "G", "Util")

    Returns:
        True if player can fill the slot
    """
    # Util can be filled by any position
    if slot_position == "Util":
        return True

    # G (guard) slot can be filled by PG or SG
    if slot_position == "G":
        return "PG" in player_positions or "SG" in player_positions

    # F (forward) slot can be filled by SF or PF
    if slot_position == "F":
        return "SF" in player_positions or "PF" in player_positions

    # Specific position slots (PG, SG, SF, PF, C) require exact match
    return slot_position in player_positions


def _get_slot_priority_for_player(player_positions: List[str], slot_position: str) -> int:
    """Get priority for assigning a player to a slot (lower is better).

    Priority order:
    1. Exact position match (PG player -> PG slot)
    2. Flex position match (PG player -> G slot)
    3. Util slot

    Args:
        player_positions: List of player's eligible positions
        slot_position: The roster slot position

    Returns:
        Priority value (lower is better)
    """
    # Exact match - highest priority
    if slot_position in player_positions:
        return 1

    # Flex positions - medium priority
    if slot_position == "G" and ("PG" in player_positions or "SG" in player_positions):
        return 2
    if slot_position == "F" and ("SF" in player_positions or "PF" in player_positions):
        return 2

    # Util - lowest priority (but still valid)
    if slot_position == "Util":
        return 3

    # Not eligible
    return 999


def optimize_roster_positions(
    players: List[Dict],
    league_roster_positions: List[str],
    players_with_games: Set[str],
    player_ranks: Optional[Dict[str, int]] = None,
) -> Dict[str, str]:
    """Optimize roster positions to maximize active players using greedy algorithm.

    Algorithm:
    1. Sort players by position eligibility count (ascending) - least flexible first
    2. For players with same flexibility, use rank as tie-breaker (lower rank = higher priority)
    3. For each player with games scheduled:
       - Try to assign to most specific eligible position slot
       - Prioritize: specific positions > flex positions (G, F) > Util
    4. Return mapping of player_key -> optimized_position

    Args:
        players: List of player dicts with 'player_key' and 'eligible_positions'
        league_roster_positions: List of position slots from league settings
                                (e.g., ["PG", "SG", "G", "SF", "PF", "F", "C", "Util", "Util", "BN", "BN"])
        players_with_games: Set of player_keys who have games scheduled
        player_ranks: Optional dict mapping player_key to Yahoo Fantasy rank (1 = best)
                      Used as tie-breaker when players have same flexibility

    Returns:
        Dictionary mapping player_key to optimized position
    """
    # Filter out inactive positions (BN, IL, IL+)
    inactive_positions = {"BN", "IL", "IL+"}
    active_slots = [pos for pos in league_roster_positions if pos not in inactive_positions]

    # Track which slots are filled
    available_slots: Dict[int, str] = {i: pos for i, pos in enumerate(active_slots)}
    player_assignments: Dict[str, str] = {}

    # Default to empty dict if no ranks provided
    if player_ranks is None:
        player_ranks = {}

    # Sort players by eligibility count (least flexible first)
    # Only consider players with games
    players_to_assign = []
    for player in players:
        player_key = player.get("player_key")
        if not player_key:
            continue

        eligible_positions = player.get("eligible_positions", [])
        
        # Log players without games for debugging
        if player_key not in players_with_games:
            logger.debug(f"Player {player_key} has no games scheduled, will be benched")
            continue
            
        if not eligible_positions:
            logger.warning(f"Player {player_key} has games but no eligible_positions data!")
            continue

        # Get player rank for tie-breaking (lower rank = better player)
        # Unranked players get 9999 to sort last among players with same flexibility
        rank = player_ranks.get(player_key, 9999)

        players_to_assign.append({
            "player_key": player_key,
            "eligible_positions": eligible_positions,
            "flexibility": len(eligible_positions),
            "rank": rank,
        })

    # Sort by flexibility (ascending), then by rank (ascending - lower rank = higher priority)
    # This ensures:
    # 1. Least flexible players are assigned first (to specific slots)
    # 2. Among players with same flexibility, higher-ranked players (lower rank number) get priority
    players_to_assign.sort(key=lambda p: (p["flexibility"], p["rank"], p["player_key"]))

    logger.info(f"Roster optimization: {len(players_to_assign)} players with games, {len(available_slots)} active slots available")
    logger.debug(f"Active slots: {active_slots}")
    logger.debug(f"Players with games: {players_with_games}")

    # Assign players to slots
    for player_info in players_to_assign:
        player_key = player_info["player_key"]
        eligible_positions = player_info["eligible_positions"]

        # Find best available slot for this player
        best_slot_idx: Optional[int] = None
        best_priority = 999

        for slot_idx, slot_pos in available_slots.items():
            if _get_eligible_slots_for_position(eligible_positions, slot_pos):
                priority = _get_slot_priority_for_player(eligible_positions, slot_pos)
                if priority < best_priority:
                    best_priority = priority
                    best_slot_idx = slot_idx

        # Assign player to best slot if found
        if best_slot_idx is not None:
            assigned_position = available_slots[best_slot_idx]
            player_assignments[player_key] = assigned_position
            del available_slots[best_slot_idx]
            logger.info(f"✓ Assigned {player_key} to {assigned_position} (eligible: {eligible_positions})")
        else:
            # No available slot - assign to BN
            player_assignments[player_key] = "BN"
            logger.warning(f"✗ No slot available for {player_key} (eligible: {eligible_positions}), forced to BN")

    # Log remaining available slots
    if available_slots:
        logger.info(f"Remaining unfilled slots: {list(available_slots.values())}")

    # Assign players without games to BN
    for player in players:
        player_key = player.get("player_key")
        if player_key and player_key not in player_assignments:
            player_assignments[player_key] = "BN"
            logger.debug(f"Player {player_key} has no games, assigned to BN")

    return player_assignments


def get_active_positions(optimized_positions: Dict[str, str]) -> Set[str]:
    """Get set of player keys that are in active positions after optimization.

    Args:
        optimized_positions: Dict mapping player_key to position

    Returns:
        Set of player keys in active positions (not BN, IL, IL+)
    """
    inactive = {"BN", "IL", "IL+"}
    return {
        player_key
        for player_key, position in optimized_positions.items()
        if position not in inactive
    }

