"""Unified player index for Yahoo Fantasy rankings and Yahoo↔NBA ID mapping.

This module provides:
1. Yahoo Fantasy player rankings storage (per league)
2. Exact name matching between Yahoo Fantasy player IDs and NBA API player IDs

Storage:
- Rankings: ~/.shams/rankings/{league_key}.json (per league)
- ID mappings: ~/.shams/player_index.json (global)

When rankings are saved, the Yahoo↔NBA ID mapping is automatically updated.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from nba_api.stats.static import players as nba_players


# =============================================================================
# Path helpers
# =============================================================================


def _get_index_path() -> Path:
    """Get the player index file path for ID mappings.

    Returns:
        Path to ~/.shams/player_index.json
    """
    cache_dir = Path.home() / ".shams"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / "player_index.json"


def _get_rankings_path(league_key: str) -> Path:
    """Get the cache file path for player rankings.

    Args:
        league_key: The Yahoo league key (e.g., "466.l.38841")

    Returns:
        Path to the cache file in ~/.shams/rankings/ directory
    """
    # Sanitize league_key to be filesystem-safe
    safe_key = league_key.replace(".", "_")
    cache_dir = Path.home() / ".shams" / "rankings"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{safe_key}.json"


# =============================================================================
# Name normalization
# =============================================================================


def _normalize_name(name: str) -> str:
    """Normalize a player name for comparison.

    Handles common variations like accents, suffixes, etc.

    Args:
        name: Player name to normalize

    Returns:
        Normalized lowercase name
    """
    import unicodedata

    # Normalize unicode and strip diacritics
    normalized = unicodedata.normalize("NFKD", name)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return ascii_text.strip().lower()


# =============================================================================
# ID Mapping Index (Global)
# =============================================================================


def _load_index() -> dict:
    """Load the player index from disk.

    Returns:
        Index dictionary or empty structure if file doesn't exist
    """
    index_path = _get_index_path()

    if not index_path.exists():
        return {
            "yahoo_id_to_nba_id": {},
            "nba_id_to_yahoo_id": {},
            "yahoo_names": {},
            "last_updated": None,
        }

    try:
        with open(index_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {
            "yahoo_id_to_nba_id": {},
            "nba_id_to_yahoo_id": {},
            "yahoo_names": {},
            "last_updated": None,
        }


def _save_index(index: dict) -> None:
    """Save the player index to disk.

    Args:
        index: Index dictionary to save
    """
    index_path = _get_index_path()

    try:
        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2)
    except IOError as e:
        print(f"Warning: Could not save player index: {e}")


def _build_nba_name_lookup() -> Dict[str, int]:
    """Build a lookup from normalized NBA player names to their IDs.

    Returns:
        Dictionary mapping normalized name to NBA player ID
    """
    lookup = {}
    for player in nba_players.get_players():
        normalized = _normalize_name(player["full_name"])
        lookup[normalized] = player["id"]
    return lookup


def get_nba_id_for_yahoo_id(yahoo_id: int) -> Optional[int]:
    """Get the NBA player ID for a Yahoo player ID.

    Args:
        yahoo_id: Yahoo Fantasy player ID (numeric)

    Returns:
        NBA player ID or None if no mapping exists
    """
    index = _load_index()
    yahoo_id_str = str(yahoo_id)

    nba_id = index.get("yahoo_id_to_nba_id", {}).get(yahoo_id_str)

    # Return None for both missing and explicitly null mappings
    if nba_id is None:
        return None

    return int(nba_id)


def get_or_create_nba_id(yahoo_id: int, player_name: str) -> Optional[int]:
    """Get NBA player ID for a Yahoo player, creating mapping if needed.

    This is the primary lookup function for waiver wire and other features.
    It checks the index first, and if the player isn't there yet, attempts
    an exact name match against NBA players and stores the result.

    Args:
        yahoo_id: Yahoo Fantasy player ID (numeric)
        player_name: Player's full name from Yahoo

    Returns:
        NBA player ID or None if no match found
    """
    index = _load_index()
    yahoo_id_str = str(yahoo_id)

    # Check if we already have this player in the index
    if yahoo_id_str in index.get("yahoo_id_to_nba_id", {}):
        nba_id = index["yahoo_id_to_nba_id"][yahoo_id_str]
        return int(nba_id) if nba_id is not None else None

    # Not in index - try exact name match against NBA players
    nba_lookup = _build_nba_name_lookup()
    normalized_name = _normalize_name(player_name)
    nba_id = nba_lookup.get(normalized_name)

    # Store the result (including None for no match)
    index.setdefault("yahoo_id_to_nba_id", {})[yahoo_id_str] = nba_id
    index.setdefault("yahoo_names", {})[yahoo_id_str] = player_name

    if nba_id is not None:
        index.setdefault("nba_id_to_yahoo_id", {})[str(nba_id)] = yahoo_id

    index["last_updated"] = datetime.now().isoformat()
    _save_index(index)

    return nba_id


def get_yahoo_id_for_nba_id(nba_id: int) -> Optional[int]:
    """Get the Yahoo player ID for an NBA player ID.

    Args:
        nba_id: NBA API player ID

    Returns:
        Yahoo Fantasy player ID or None if no mapping exists
    """
    index = _load_index()
    nba_id_str = str(nba_id)

    yahoo_id = index.get("nba_id_to_yahoo_id", {}).get(nba_id_str)

    if yahoo_id is None:
        return None

    return int(yahoo_id)


def get_player_name_by_yahoo_id(yahoo_id: int) -> Optional[str]:
    """Get the player name for a Yahoo player ID from our index.

    Args:
        yahoo_id: Yahoo Fantasy player ID (numeric)

    Returns:
        Player name or None if not in index
    """
    index = _load_index()
    return index.get("yahoo_names", {}).get(str(yahoo_id))


def _update_id_mappings_from_players(players: List[dict]) -> dict:
    """Update Yahoo↔NBA ID mappings from a list of Yahoo players.

    Args:
        players: List of player dicts from Yahoo API

    Returns:
        Statistics about the indexing operation
    """
    index = _load_index()
    nba_lookup = _build_nba_name_lookup()

    stats = {
        "total_yahoo_players": 0,
        "exact_matches": 0,
        "no_match": 0,
    }

    for player in players:
        yahoo_id = player.get("player_id")
        if yahoo_id is None:
            continue

        stats["total_yahoo_players"] += 1
        yahoo_id_str = str(yahoo_id)

        # Extract player name
        name_data = player.get("name", {})
        if isinstance(name_data, dict):
            player_name = name_data.get("full", "")
        else:
            player_name = str(name_data) if name_data else ""

        if not player_name:
            continue

        # Store the Yahoo name for reference
        index.setdefault("yahoo_names", {})[yahoo_id_str] = player_name

        # Try exact name match against NBA players
        normalized_name = _normalize_name(player_name)
        nba_id = nba_lookup.get(normalized_name)

        if nba_id is not None:
            # Found exact match
            stats["exact_matches"] += 1
            index.setdefault("yahoo_id_to_nba_id", {})[yahoo_id_str] = nba_id
            index.setdefault("nba_id_to_yahoo_id", {})[str(nba_id)] = yahoo_id
        else:
            # No match - explicitly store None so we don't keep trying
            stats["no_match"] += 1
            index.setdefault("yahoo_id_to_nba_id", {})[yahoo_id_str] = None

    index["last_updated"] = datetime.now().isoformat()
    _save_index(index)

    return stats


def get_index_stats() -> dict:
    """Get statistics about the current player index.

    Returns:
        Dictionary with index statistics
    """
    index = _load_index()

    yahoo_to_nba = index.get("yahoo_id_to_nba_id", {})
    matched = sum(1 for v in yahoo_to_nba.values() if v is not None)
    unmatched = sum(1 for v in yahoo_to_nba.values() if v is None)

    return {
        "total_yahoo_players": len(yahoo_to_nba),
        "matched_to_nba": matched,
        "unmatched": unmatched,
        "last_updated": index.get("last_updated"),
    }


def clear_index() -> None:
    """Clear the player index file (ID mappings only)."""
    index_path = _get_index_path()
    if index_path.exists():
        try:
            index_path.unlink()
        except IOError:
            pass


# =============================================================================
# Rankings Cache (Per League)
# =============================================================================


def load_rankings(league_key: str) -> Optional[List[dict]]:
    """Load cached player rankings from file.

    Args:
        league_key: The Yahoo league key

    Returns:
        List of player dictionaries with rank field, or None if cache doesn't exist
    """
    cache_path = _get_rankings_path(league_key)

    if not cache_path.exists():
        return None

    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("players", [])
    except (json.JSONDecodeError, IOError):
        return None


def save_rankings(league_key: str, players: List[dict]) -> None:
    """Save player rankings to cache file with current timestamp.

    Also updates the global Yahoo↔NBA ID mapping index.

    Args:
        league_key: The Yahoo league key
        players: List of player dictionaries with rank field
    """
    cache_path = _get_rankings_path(league_key)

    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "players": players,
                    "timestamp": datetime.now().isoformat(),
                    "player_count": len(players),
                },
                f,
                indent=2,
            )
    except (IOError, TypeError) as e:
        print(f"Warning: Could not write rankings cache: {e}")

    # Also update the Yahoo↔NBA ID mappings
    _update_id_mappings_from_players(players)


def get_player_rank(league_key: str, player_key: str) -> Optional[int]:
    """Get the rank for a specific player by player key.

    Args:
        league_key: The Yahoo league key
        player_key: The player's Yahoo key (e.g., "466.p.5432")

    Returns:
        Player's rank (1-indexed) or None if not found
    """
    players = load_rankings(league_key)
    if not players:
        return None

    for player in players:
        if player.get("player_key") == player_key:
            return player.get("rank")

    return None


def get_player_rank_by_id(league_key: str, player_id: int) -> Optional[int]:
    """Get the rank for a specific player by Yahoo player ID.

    Args:
        league_key: The Yahoo league key
        player_id: The player's Yahoo ID (numeric)

    Returns:
        Player's rank (1-indexed) or None if not found
    """
    players = load_rankings(league_key)
    if not players:
        return None

    for player in players:
        if player.get("player_id") == player_id:
            return player.get("rank")

    return None


def get_player_rank_by_name(league_key: str, player_name: str) -> Optional[int]:
    """Get the rank for a specific player by name.

    Args:
        league_key: The Yahoo league key
        player_name: The player's full name

    Returns:
        Player's rank (1-indexed) or None if not found
    """
    players = load_rankings(league_key)
    if not players:
        return None

    # Normalize the search name for comparison
    search_name = player_name.lower().strip()

    for player in players:
        name_data = player.get("name", {})
        if isinstance(name_data, dict):
            full_name = name_data.get("full", "").lower().strip()
        else:
            full_name = str(name_data).lower().strip()

        if full_name == search_name:
            return player.get("rank")

    return None


def get_player_rank_by_nba_id(league_key: str, nba_player_id: int) -> Optional[int]:
    """Get the rank for a specific player by NBA player ID.

    Uses the Yahoo↔NBA ID mapping to find the Yahoo player, then looks up rank.

    Args:
        league_key: The Yahoo league key
        nba_player_id: The player's NBA API ID (e.g., 1628983 for SGA)

    Returns:
        Player's rank (1-indexed) or None if not found
    """
    # First try to use our ID mapping
    yahoo_id = get_yahoo_id_for_nba_id(nba_player_id)
    if yahoo_id is not None:
        rank = get_player_rank_by_id(league_key, yahoo_id)
        if rank is not None:
            return rank

    # Fallback: Look up player name from NBA API and search by name
    for player in nba_players.get_players():
        if player["id"] == nba_player_id:
            return get_player_rank_by_name(league_key, player["full_name"])

    return None


def get_all_player_ranks(league_key: str) -> Dict[str, int]:
    """Get a mapping of all player keys to their ranks.

    Args:
        league_key: The Yahoo league key

    Returns:
        Dictionary mapping player_key to rank
    """
    players = load_rankings(league_key)
    if not players:
        return {}

    return {
        player.get("player_key"): player.get("rank")
        for player in players
        if player.get("player_key") and player.get("rank")
    }


def is_rankings_cache_stale(league_key: str, max_age_hours: float = 24.0) -> bool:
    """Check if the rankings cache is stale.

    Args:
        league_key: The Yahoo league key
        max_age_hours: Maximum age in hours before cache is considered stale

    Returns:
        True if cache doesn't exist or is older than max_age_hours
    """
    cache_path = _get_rankings_path(league_key)

    if not cache_path.exists():
        return True

    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            timestamp_str = data.get("timestamp")
            if not timestamp_str:
                return True

            timestamp = datetime.fromisoformat(timestamp_str)
            age_hours = (datetime.now() - timestamp).total_seconds() / 3600
            return age_hours > max_age_hours
    except (json.JSONDecodeError, IOError, ValueError):
        return True


def get_rankings_cache_metadata(league_key: str) -> Optional[Dict[str, Any]]:
    """Get metadata about the rankings cache.

    Args:
        league_key: The Yahoo league key

    Returns:
        Dictionary with cache metadata or None if cache doesn't exist
    """
    cache_path = _get_rankings_path(league_key)

    if not cache_path.exists():
        return None

    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            timestamp_str = data.get("timestamp")
            player_count = data.get("player_count", len(data.get("players", [])))

            result: Dict[str, Any] = {
                "player_count": player_count,
                "cache_path": str(cache_path),
            }

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


def clear_rankings_cache(league_key: str) -> None:
    """Delete the rankings cache file if it exists.

    Args:
        league_key: The Yahoo league key
    """
    cache_path = _get_rankings_path(league_key)

    if cache_path.exists():
        try:
            cache_path.unlink()
        except IOError:
            pass
