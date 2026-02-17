"""Stat name mapping utilities for converting between different formats.

Maps stat names/abbreviations between different representations:
- Yahoo stat names (e.g., "3PTM", "FG%")
- Box score cache field names (lowercase: "threes", "fg_pct")
- Game field names (UPPERCASE: "FG3M", "FG_PCT")
"""

from __future__ import annotations

from typing import Dict


def build_stat_name_to_cache_mapping() -> Dict[str, str]:
    """Map stat names/abbreviations to boxscore cache field names (lowercase).

    Used for accessing season stats from the boxscore cache which stores
    per-game averages in lowercase field names.

    Returns:
        Dictionary mapping Yahoo stat names to cache field names

    Examples:
        >>> mapping = build_stat_name_to_cache_mapping()
        >>> mapping["3PTM"]
        'threes'
        >>> mapping["FG%"]
        'fg_pct'
    """
    return {
        # Percentage stats
        "FG%": "fg_pct",
        "FT%": "ft_pct",
        # Counting stats
        "3PTM": "threes",
        "3PM": "threes",
        "PTS": "points",
        "REB": "rebounds",
        "AST": "assists",
        "ST": "steals",
        "STL": "steals",
        "BLK": "blocks",
        "TO": "turnovers",
    }


def build_stat_name_to_game_field_mapping() -> Dict[str, str]:
    """Map stat names/abbreviations to boxscore game field names (UPPERCASE).

    Used for accessing individual game stats from cached box scores which store
    per-game stats in UPPERCASE field names following NBA API V3 format.

    Returns:
        Dictionary mapping Yahoo stat names to game field names

    Examples:
        >>> mapping = build_stat_name_to_game_field_mapping()
        >>> mapping["3PTM"]
        'FG3M'
        >>> mapping["FG%"]
        'FG_PCT'
    """
    return {
        # Percentage stats - stored but computed from makes/attempts
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


def get_cache_field_for_stat(stat_name: str) -> str:
    """Get the cache field name for a given stat name.

    Args:
        stat_name: Yahoo stat name (e.g., "3PTM", "FG%")

    Returns:
        Cache field name (e.g., "threes", "fg_pct"), or empty string if not found
    """
    mapping = build_stat_name_to_cache_mapping()
    return mapping.get(stat_name, "")


def get_game_field_for_stat(stat_name: str) -> str:
    """Get the game field name for a given stat name.

    Args:
        stat_name: Yahoo stat name (e.g., "3PTM", "FG%")

    Returns:
        Game field name (e.g., "FG3M", "FG_PCT"), or empty string if not found
    """
    mapping = build_stat_name_to_game_field_mapping()
    return mapping.get(stat_name, "")


def is_percentage_stat(stat_name: str) -> bool:
    """Check if a stat is a percentage stat.

    Percentage stats should not be summed but rather computed from
    makes and attempts (e.g., FG% = FGM / FGA).

    Args:
        stat_name: Stat name to check

    Returns:
        True if stat is a percentage stat
    """
    return "%" in stat_name


def get_stat_display_name(stat: Dict) -> str:
    """Get the display name for a stat from its metadata.

    Tries display_name first, then name, then abbreviation.

    Args:
        stat: Stat metadata dictionary

    Returns:
        Display name or empty string
    """
    return stat.get("display_name") or stat.get("name") or stat.get("abbr", "")
