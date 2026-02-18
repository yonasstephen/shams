"""Cache management for waiver wire player data."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def get_cache_path(league_key: str) -> Path:
    """Get the cache file path for a specific league.

    Args:
        league_key: The Yahoo league key (e.g., "466.l.38841")

    Returns:
        Path to the cache file in ~/.shams/waiver/ directory
    """
    # Sanitize league_key to be filesystem-safe
    safe_key = league_key.replace(".", "_")
    cache_dir = Path.home() / ".shams" / "waiver"
    cache_dir.mkdir(parents=True, exist_ok=True)

    return cache_dir / f"{safe_key}.json"


def load_cached_players(
    league_key: str, max_age_hours: Optional[float] = None
) -> Optional[List[dict]]:
    """Load cached player list from file.

    Args:
        league_key: The Yahoo league key
        max_age_hours: Maximum cache age in hours. If None, no age check is performed.
                      If cache is older than this, returns None to force refresh.

    Returns:
        List of player dictionaries if cache exists and is fresh, None otherwise
    """
    cache_path = get_cache_path(league_key)

    if not cache_path.exists():
        return None

    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)

            # Check cache age if max_age_hours is specified
            if max_age_hours is not None:
                timestamp_str = data.get("timestamp")
                if timestamp_str:
                    timestamp = datetime.fromisoformat(timestamp_str)
                    age_hours = (datetime.now() - timestamp).total_seconds() / 3600
                    if age_hours > max_age_hours:
                        return None

            return data.get("players", [])
    except (json.JSONDecodeError, IOError, ValueError):
        # If cache is corrupted, treat as if it doesn't exist
        return None


def save_cached_players(league_key: str, players: List[dict]) -> None:
    """Save player list to cache file with current timestamp.

    Args:
        league_key: The Yahoo league key
        players: List of player dictionaries to cache
    """
    cache_path = get_cache_path(league_key)

    try:
        # Ensure all players are properly serialized to dicts
        serialized_players = []
        for player in players:
            if hasattr(player, "serialized"):
                serialized_players.append(player.serialized())
            elif isinstance(player, dict):
                serialized_players.append(player)
            else:
                # Try to convert to dict if possible
                try:
                    serialized_players.append(dict(player))
                except (TypeError, ValueError):
                    # Skip non-serializable players
                    print(f"Warning: Skipping non-serializable player: {type(player)}")
                    continue

        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "players": serialized_players,
                    "timestamp": datetime.now().isoformat(),
                },
                f,
                indent=2,
            )
    except (IOError, TypeError) as e:
        # Log but don't fail if we can't write cache
        print(f"Warning: Could not write waiver cache: {e}")


def get_cache_metadata(league_key: str) -> Optional[Dict[str, Any]]:
    """Get metadata about the cache without loading all players.

    Args:
        league_key: The Yahoo league key

    Returns:
        Dictionary with cache metadata (timestamp, player_count) or None if cache doesn't exist
    """
    cache_path = get_cache_path(league_key)

    if not cache_path.exists():
        return None

    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            timestamp_str = data.get("timestamp")
            players = data.get("players", [])

            result = {"player_count": len(players), "cache_path": str(cache_path)}

            if timestamp_str:
                try:
                    timestamp = datetime.fromisoformat(timestamp_str)
                    result["timestamp"] = timestamp_str
                    result["age_hours"] = (
                        datetime.now() - timestamp
                    ).total_seconds() / 3600
                except ValueError:
                    pass

            return result
    except (json.JSONDecodeError, IOError):
        return None


def clear_cache(league_key: str) -> None:
    """Delete the cache file if it exists.

    Args:
        league_key: The Yahoo league key
    """
    cache_path = get_cache_path(league_key)

    if cache_path.exists():
        try:
            cache_path.unlink()
        except IOError:
            # Silently ignore if we can't delete
            pass


def clear_all_caches() -> None:
    """Delete all waiver cache files for all leagues."""
    cache_dir = Path.home() / ".shams" / "waiver"
    if cache_dir.exists():
        for cache_file in cache_dir.glob("*.json"):
            try:
                cache_file.unlink()
            except IOError:
                pass  # Silently ignore if we can't delete
