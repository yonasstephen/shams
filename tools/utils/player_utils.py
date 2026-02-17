"""Utilities for working with player data."""

from __future__ import annotations

from typing import Dict, List, Optional


def get_player_key(player: dict) -> Optional[str]:
    """Extract player key from a player dict.

    Args:
        player: Player dictionary

    Returns:
        Player key or None if not found
    """
    return player.get("player_key")


def deduplicate_players(roster: Dict[str, List[dict]]) -> Dict[str, dict]:
    """Deduplicate players from a roster that has same players across multiple dates.

    When rosters are collected for multiple dates, the same player appears once per date.
    This function extracts unique players keyed by their player_key.

    Args:
        roster: Dictionary mapping date strings to lists of player dicts

    Returns:
        Dictionary mapping player keys to player dicts (one per unique player)

    Example:
        >>> roster = {
        ...     "2024-11-01": [{"player_key": "nba.p.123", "name": "Player A"}],
        ...     "2024-11-02": [{"player_key": "nba.p.123", "name": "Player A"}]
        ... }
        >>> unique = deduplicate_players(roster)
        >>> len(unique)
        1
        >>> "nba.p.123" in unique
        True
    """
    unique_players: Dict[str, dict] = {}

    for players in roster.values():
        for player in players:
            player_key = get_player_key(player)
            if player_key and player_key not in unique_players:
                unique_players[player_key] = player

    return unique_players


def deduplicate_player_list(players: List[dict]) -> Dict[str, dict]:
    """Deduplicate a flat list of players by player_key.

    Args:
        players: List of player dictionaries

    Returns:
        Dictionary mapping player keys to player dicts
    """
    unique_players: Dict[str, dict] = {}

    for player in players:
        player_key = get_player_key(player)
        if player_key and player_key not in unique_players:
            unique_players[player_key] = player

    return unique_players


def get_player_name(player: dict) -> str:
    """Extract player name from a player dict.

    Handles both nested {"name": {"full": "..."}} and simple formats.

    Args:
        player: Player dictionary

    Returns:
        Player's full name or empty string if not found
    """
    name = player.get("name", {})

    if isinstance(name, dict):
        return name.get("full", "")
    elif isinstance(name, str):
        return name
    else:
        return ""


def get_player_position(player: dict) -> str:
    """Extract player's selected position from a player dict.

    Handles both nested {"selected_position": {"position": "..."}} and simple formats.

    Args:
        player: Player dictionary

    Returns:
        Player's position or empty string if not found
    """
    selected_position = player.get("selected_position")

    if isinstance(selected_position, dict):
        return selected_position.get("position", "")
    elif isinstance(selected_position, str):
        return selected_position
    else:
        return ""


def get_player_eligible_positions(player: dict) -> List[str]:
    """Extract player's eligible positions from a player dict.

    Handles both nested and simple formats from Yahoo API.
    Eligible positions indicate which roster slots a player can fill.

    Args:
        player: Player dictionary from Yahoo API

    Returns:
        List of eligible position strings (e.g., ["PG", "SG"]) or empty list if not found
    """
    eligible_positions = player.get("eligible_positions")

    if isinstance(eligible_positions, list):
        # Already a list of strings
        if all(isinstance(p, str) for p in eligible_positions):
            return eligible_positions
        # List of position objects - extract position field
        result = []
        for pos_entry in eligible_positions:
            if isinstance(pos_entry, dict):
                pos = pos_entry.get("position", "")
            elif isinstance(pos_entry, str):
                pos = pos_entry
            else:
                pos = str(pos_entry) if pos_entry else ""
            if pos:
                result.append(pos)
        return result
    elif isinstance(eligible_positions, str):
        # Single position as string
        return [eligible_positions]
    else:
        return []
