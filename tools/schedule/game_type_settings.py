"""Game type settings for filtering fantasy-eligible NBA games.

This module provides configuration for which NBA game types should count
towards Yahoo Fantasy Basketball stats. Games like NBA Cup Finals, preseason,
All-Star, and playoffs can be toggled on/off based on league rules.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional


# Default settings for which game types count towards fantasy
DEFAULT_SETTINGS: Dict[str, bool] = {
    "regular_season": True,           # gameLabel="" and gameSubtype=""
    "nba_cup_group_stage": True,      # gameSubtype="in-season"
    "nba_cup_knockout": True,         # gameSubtype="in-season-knockout" (excl. Championship)
    "nba_cup_final": False,           # gameSubLabel="Championship"
    "preseason": False,               # gameLabel="Preseason"
    "all_star": False,                # gameLabel contains "All-Star"
    "play_in": False,                 # gameLabel contains "Play-In"
    "playoffs_first_round": False,    # gameLabel contains "First Round"
    "playoffs_conf_semis": False,     # gameLabel contains "Conf. Semifinals"
    "playoffs_conf_finals": False,    # gameLabel contains "Conf. Finals"
    "nba_finals": False,              # gameLabel="NBA Finals"
    "global_games": True,             # gameSubtype="Global Games" - regular season games played internationally
}

# Human-readable descriptions for each setting
SETTING_DESCRIPTIONS: Dict[str, str] = {
    "regular_season": "Standard regular season games",
    "nba_cup_group_stage": "NBA Cup group stage games",
    "nba_cup_knockout": "NBA Cup knockout rounds (Quarterfinals, Semifinals)",
    "nba_cup_final": "NBA Cup Championship game",
    "preseason": "Preseason games",
    "all_star": "All-Star events",
    "play_in": "Play-In Tournament",
    "playoffs_first_round": "Playoffs First Round",
    "playoffs_conf_semis": "Playoffs Conference Semifinals",
    "playoffs_conf_finals": "Playoffs Conference Finals",
    "nba_finals": "NBA Finals",
    "global_games": "NBA games in Paris, London, Mexico City, etc. (count as regular season)",
}

# Categories for UI grouping
SETTING_CATEGORIES: Dict[str, list] = {
    "Regular Season": ["regular_season"],
    "NBA Cup": ["nba_cup_group_stage", "nba_cup_knockout", "nba_cup_final"],
    "Playoffs": [
        "play_in",
        "playoffs_first_round",
        "playoffs_conf_semis",
        "playoffs_conf_finals",
        "nba_finals",
    ],
    "Other": ["preseason", "all_star", "global_games"],
}


def get_settings_file_path() -> Path:
    """Get the path to the game type settings file.

    Returns:
        Path to ~/.shams/game_type_settings.json
    """
    settings_dir = Path.home() / ".shams"
    settings_dir.mkdir(parents=True, exist_ok=True)
    return settings_dir / "game_type_settings.json"


def load_settings() -> Dict[str, bool]:
    """Load game type settings from file.

    Returns settings merged with defaults to handle new settings added in updates.

    Returns:
        Dictionary of setting name to boolean value
    """
    settings_file = get_settings_file_path()

    # Start with defaults
    settings = DEFAULT_SETTINGS.copy()

    if settings_file.exists():
        try:
            with open(settings_file, "r", encoding="utf-8") as f:
                saved_settings = json.load(f)

            # Merge saved settings (only override known keys)
            for key, value in saved_settings.items():
                if key in settings and isinstance(value, bool):
                    settings[key] = value
        except (json.JSONDecodeError, IOError):
            # If file is corrupted, use defaults
            pass

    return settings


def save_settings(settings: Dict[str, bool]) -> bool:
    """Save game type settings to file.

    Args:
        settings: Dictionary of setting name to boolean value

    Returns:
        True if saved successfully, False otherwise
    """
    settings_file = get_settings_file_path()

    # Only save known settings
    filtered_settings = {
        key: value
        for key, value in settings.items()
        if key in DEFAULT_SETTINGS and isinstance(value, bool)
    }

    try:
        with open(settings_file, "w", encoding="utf-8") as f:
            json.dump(filtered_settings, f, indent=2)
        return True
    except IOError:
        return False


def get_game_type(row: Any) -> Optional[str]:
    """Determine the game type category from a schedule row.

    Args:
        row: A row from the NBA API schedule DataFrame

    Returns:
        The setting key that matches this game type, or None if unknown
    """
    game_subtype = row.get("gameSubtype", "") or ""
    game_label = row.get("gameLabel", "") or ""
    game_sublabel = row.get("gameSubLabel", "") or ""

    # Check in order of specificity

    # NBA Cup Final (Championship)
    if game_subtype == "in-season-knockout" and game_sublabel == "Championship":
        return "nba_cup_final"

    # NBA Cup Knockout (Quarterfinals, Semifinals)
    if game_subtype == "in-season-knockout":
        return "nba_cup_knockout"

    # NBA Cup Group Stage
    if game_subtype == "in-season":
        return "nba_cup_group_stage"

    # Global Games
    if game_subtype == "Global Games":
        return "global_games"

    # Preseason
    if game_label == "Preseason":
        return "preseason"

    # All-Star events
    if "All-Star" in game_label:
        return "all_star"

    # Play-In Tournament
    if "Play-In" in game_label:
        return "play_in"

    # NBA Finals
    if game_label == "NBA Finals":
        return "nba_finals"

    # Conference Finals
    if "Conf. Finals" in game_label:
        return "playoffs_conf_finals"

    # Conference Semifinals
    if "Conf. Semifinals" in game_label:
        return "playoffs_conf_semis"

    # First Round
    if "First Round" in game_label:
        return "playoffs_first_round"

    # Regular season (empty label and subtype)
    if not game_label and not game_subtype:
        return "regular_season"

    # Unknown game type - default to regular season behavior
    return "regular_season"


def is_fantasy_eligible_game(row: Any, settings: Optional[Dict[str, bool]] = None) -> bool:
    """Check if a game counts towards Yahoo Fantasy stats based on settings.

    Args:
        row: A row from the NBA API schedule DataFrame
        settings: Optional settings dict. If None, loads from file.

    Returns:
        True if the game should count towards fantasy stats
    """
    if settings is None:
        settings = load_settings()

    game_type = get_game_type(row)

    if game_type is None:
        # Unknown game type - exclude by default
        return False

    # Return the setting value (True = counts, False = doesn't count)
    return settings.get(game_type, False)


def get_settings_with_metadata() -> Dict[str, Any]:
    """Get settings with descriptions and categories for API response.

    Returns:
        Dictionary containing settings, descriptions, and categories
    """
    settings = load_settings()

    return {
        "settings": settings,
        "descriptions": SETTING_DESCRIPTIONS,
        "categories": SETTING_CATEGORIES,
        "defaults": DEFAULT_SETTINGS,
    }
