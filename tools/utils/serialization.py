"""Utilities for serializing yfpy objects and extracting data from them."""

from __future__ import annotations

from typing import Any, Dict, Optional


def serialize_yfpy_object(obj: Any) -> Optional[Dict]:
    """Convert a yfpy object to a dictionary.

    Args:
        obj: Object to serialize (dict, yfpy object, or other)

    Returns:
        Dictionary representation, or None if object cannot be serialized
    """
    if obj is None:
        return None

    if isinstance(obj, dict):
        return obj

    # Try yfpy's serialized() method first
    if hasattr(obj, "serialized"):
        return obj.serialized()

    # Fall back to __dict__
    if hasattr(obj, "__dict__"):
        return obj.__dict__

    return None


def extract_stats_from_player(player: dict) -> Dict[str, float]:
    """Extract stat dictionary from a player object.

    Handles both dict and yfpy Player objects, extracting the stats
    from player_stats container.

    Args:
        player: Player dict or yfpy Player object

    Returns:
        Dictionary mapping stat_id to float value
    """
    if not isinstance(player, dict):
        player = serialize_yfpy_object(player)

    if not player:
        return {}

    stats_container = player.get("player_stats", {})
    stats_container = serialize_yfpy_object(stats_container) or stats_container

    # Extract stats array
    stat_entries = (
        stats_container.get("stats")
        if isinstance(stats_container, dict)
        else stats_container
    )

    result: Dict[str, float] = {}
    for stat_entry in stat_entries or []:
        # Serialize the stat entry
        stat_entry = serialize_yfpy_object(stat_entry) or stat_entry

        # Get the stat object
        stat_obj = (
            stat_entry.get("stat") if isinstance(stat_entry, dict) else stat_entry
        )
        stat_obj = serialize_yfpy_object(stat_obj) or stat_obj

        if not isinstance(stat_obj, dict):
            continue

        stat_id = str(stat_obj.get("stat_id"))
        try:
            value = float(stat_obj.get("value", 0.0))
        except (TypeError, ValueError):
            value = 0.0
        result[stat_id] = value

    return result


def extract_team_stats(team_data: dict) -> Dict[str, float]:
    """Extract team stats from a team data object.

    Args:
        team_data: Team data dict or yfpy Team object

    Returns:
        Dictionary mapping stat_id to float value
    """
    if not isinstance(team_data, dict):
        team_data = serialize_yfpy_object(team_data)

    if not team_data:
        return {}

    stats_container = team_data.get("team_stats")
    stats_container = serialize_yfpy_object(stats_container) or stats_container

    # Extract stats array
    stats_list = []
    if isinstance(stats_container, dict):
        stats_list = stats_container.get("stats", [])
    elif hasattr(stats_container, "stats"):
        stats_list = stats_container.stats

    result: Dict[str, float] = {}
    for stat_entry in stats_list or []:
        stat_obj = serialize_yfpy_object(stat_entry) or stat_entry

        if isinstance(stat_obj, dict):
            stat_obj = stat_obj.get("stat", stat_obj)
            stat_obj = serialize_yfpy_object(stat_obj) or stat_obj

        if not isinstance(stat_obj, dict):
            continue

        stat_id = str(stat_obj.get("stat_id"))
        try:
            value = float(stat_obj.get("value", 0.0))
        except (TypeError, ValueError):
            value = 0.0
        result[stat_id] = value

    return result


def extract_team_points(team_data: dict) -> Dict[str, float]:
    """Extract team points (wins/losses/ties) from a team data object.

    Args:
        team_data: Team data dict or yfpy Team object

    Returns:
        Dictionary with points breakdown
    """
    if not isinstance(team_data, dict):
        team_data = serialize_yfpy_object(team_data)

    if not team_data:
        return {}

    points_container = team_data.get("team_points", {})
    points_container = serialize_yfpy_object(points_container) or points_container

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


def serialize_team_entry(entry: Any) -> Optional[dict]:
    """Serialize a team entry from a matchup.

    Args:
        entry: Team entry object (may be nested in {"team": ...} structure)

    Returns:
        Serialized team dict or None if unable to serialize
    """
    team = entry
    if isinstance(entry, dict):
        team = entry.get("team", entry)

    return serialize_yfpy_object(team)


def ensure_string(value: Any) -> Optional[str]:
    """Ensure a value is a string, handling bytes and other types.

    Args:
        value: Value to convert to string

    Returns:
        String representation or None if value is None
    """
    if value is None:
        return None

    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore")

    if isinstance(value, str):
        return value

    return str(value)
