"""Box score caching system for storing and indexing NBA game data."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def get_cache_dir() -> Path:
    """Get the box score cache directory.

    Returns:
        Path to ~/.shams/boxscores/
    """
    cache_dir = Path.home() / ".shams" / "boxscores"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _get_games_dir(season: str) -> Path:
    """Get the games directory for a season."""
    games_dir = get_cache_dir() / "games" / season
    games_dir.mkdir(parents=True, exist_ok=True)
    return games_dir


def _get_players_dir(season: str) -> Path:
    """Get the players directory for a season."""
    players_dir = get_cache_dir() / "players" / season
    players_dir.mkdir(parents=True, exist_ok=True)
    return players_dir


def _get_season_stats_dir(season: str) -> Path:
    """Get the season stats directory for a season."""
    stats_dir = get_cache_dir() / "season_stats" / season
    stats_dir.mkdir(parents=True, exist_ok=True)
    return stats_dir


def clear_season_cache(season: str) -> None:
    """Clear cached box scores and player indexes for a specific season only.

    This removes only data for the specified season:
    - Game box scores for this season
    - Player indexes for this season
    - Season stats for this season
    - Metadata for this season

    Other seasons' data is preserved.

    Args:
        season: Season string (e.g., "2025-26") to clear
    """
    import shutil

    cache_dir = get_cache_dir()

    # Remove games directory for this season
    games_dir = cache_dir / "games" / season
    if games_dir.exists():
        shutil.rmtree(games_dir)
        print(f"✓ Cleared game cache for {season}: {games_dir}")

    # Remove players directory for this season
    players_dir = cache_dir / "players" / season
    if players_dir.exists():
        shutil.rmtree(players_dir)
        print(f"✓ Cleared player indexes for {season}: {players_dir}")

    # Remove season stats directory for this season
    stats_dir = cache_dir / "season_stats" / season
    if stats_dir.exists():
        shutil.rmtree(stats_dir)
        print(f"✓ Cleared season stats for {season}: {stats_dir}")

    # Remove season-specific metadata
    metadata_file = cache_dir / f"metadata_{season}.json"
    if metadata_file.exists():
        metadata_file.unlink()
        print(f"✓ Cleared metadata for {season}: {metadata_file}")

    print(f"✓ Box score cache for season {season} cleared!")


def clear_cache() -> None:
    """Clear ALL cached box scores and player indexes for ALL seasons.

    WARNING: This removes everything. Use clear_season_cache(season) to
    clear only a specific season's data.

    This removes:
    - All game box scores (all seasons)
    - All player indexes (all seasons)
    - All season stats (all seasons)
    - All metadata files

    Use this only when:
    - Starting completely fresh
    - Cache is corrupted beyond repair
    """
    import shutil

    cache_dir = get_cache_dir()

    # Remove games directory (all seasons)
    games_dir = cache_dir / "games"
    if games_dir.exists():
        shutil.rmtree(games_dir)
        print(f"✓ Cleared game cache: {games_dir}")

    # Remove players directory (all seasons)
    players_dir = cache_dir / "players"
    if players_dir.exists():
        shutil.rmtree(players_dir)
        print(f"✓ Cleared player indexes: {players_dir}")

    # Remove season stats directory (all seasons)
    stats_dir = cache_dir / "season_stats"
    if stats_dir.exists():
        shutil.rmtree(stats_dir)
        print(f"✓ Cleared season stats: {stats_dir}")

    # Remove all metadata files (legacy and season-specific)
    metadata_file = cache_dir / "metadata.json"
    if metadata_file.exists():
        metadata_file.unlink()
        print(f"✓ Cleared metadata: {metadata_file}")

    # Remove season-specific metadata files
    for meta_file in cache_dir.glob("metadata_*.json"):
        meta_file.unlink()
        print(f"✓ Cleared metadata: {meta_file}")

    print("✓ Box score cache completely cleared!")


def _get_metadata_path(season: str | None = None) -> Path:
    """Get the metadata file path.
    
    Args:
        season: Season string (e.g., "2025-26"). If provided, returns
                season-specific metadata path. If None, returns the
                legacy global metadata path for backward compatibility.
    
    Returns:
        Path to metadata file
    """
    if season:
        return get_cache_dir() / f"metadata_{season}.json"
    return get_cache_dir() / "metadata.json"


def load_metadata(season: str | None = None) -> dict:
    """Load cache metadata.

    Args:
        season: Season string (e.g., "2025-26"). If provided, loads
                season-specific metadata. If None, loads legacy global metadata.

    Returns:
        Metadata dictionary or empty dict if file doesn't exist
    """
    metadata_path = _get_metadata_path(season)

    if not metadata_path.exists():
        return {
            "season": season or "",
            "last_updated": None,
            "games_cached": 0,
            "players_indexed": 0,
            "date_range": {"start": None, "end": None},
        }

    try:
        with open(metadata_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {
            "season": season or "",
            "last_updated": None,
            "games_cached": 0,
            "players_indexed": 0,
            "date_range": {"start": None, "end": None},
        }


def save_metadata(data: dict, season: str | None = None) -> None:
    """Save cache metadata.

    Args:
        data: Metadata dictionary to save
        season: Season string (e.g., "2025-26"). If provided, saves to
                season-specific metadata file. If None, saves to legacy global file.
    """
    metadata_path = _get_metadata_path(season)

    try:
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except IOError as e:
        print(f"Warning: Could not save metadata: {e}")


def load_game(game_id: str, season: str) -> Optional[dict]:
    """Load a game box score from cache.

    Args:
        game_id: NBA game ID
        season: Season (e.g., "2025-26")

    Returns:
        Game data dictionary or None if not found
    """
    games_dir = _get_games_dir(season)

    # Find game file (format: YYYYMMDD_gameid.json)
    game_files = list(games_dir.glob(f"*_{game_id}.json"))

    if not game_files:
        return None

    try:
        with open(game_files[0], "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def load_date_boxscore(game_date: str, season: str = "2025-26") -> Optional[Dict[str, dict]]:
    """Load all game box scores for a specific date.

    Args:
        game_date: Date in YYYY-MM-DD format
        season: Season (e.g., "2025-26")

    Returns:
        Dictionary mapping game_id to game data, or None if no games found
    """
    games_dir = _get_games_dir(season)

    # Convert date to filename format (YYYYMMDD)
    date_prefix = game_date.replace("-", "")

    # Find all game files for this date
    game_files = list(games_dir.glob(f"{date_prefix}_*.json"))

    if not game_files:
        return None

    result = {}
    for game_file in game_files:
        try:
            with open(game_file, "r") as f:
                game_data = json.load(f)
                game_id = game_data.get("game_id", game_file.stem.split("_", 1)[1])
                result[game_id] = game_data
        except (json.JSONDecodeError, IOError):
            continue

    return result if result else None


def save_game(game_id: str, season: str, game_date: str, data: dict) -> None:
    """Save a game box score to cache.

    Args:
        game_id: NBA game ID
        season: Season (e.g., "2025-26")
        game_date: Game date in YYYY-MM-DD format
        data: Game data dictionary
    """
    games_dir = _get_games_dir(season)

    # Format: YYYYMMDD_gameid.json
    date_str = game_date.replace("-", "")
    game_file = games_dir / f"{date_str}_{game_id}.json"

    try:
        with open(game_file, "w") as f:
            json.dump(data, f, indent=2)
    except IOError as e:
        print(f"Warning: Could not save game {game_id}: {e}")


def load_player_games(player_id: int, season: str) -> Optional[dict]:
    """Load a player's game index from cache.

    Args:
        player_id: NBA player ID
        season: Season string (e.g., "2025-26")

    Returns:
        Player data dictionary or None if not found
    """
    if not season:
        raise ValueError("season must be provided to load_player_games")
    players_dir = _get_players_dir(season)

    # Find player file (format: <id>_Name.json)
    player_files = list(players_dir.glob(f"{player_id}_*.json"))

    if not player_files:
        return None

    try:
        with open(player_files[0], "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def save_player_games(player_id: int, player_name: str, data: dict,
                      season: str) -> None:
    """Save a player's game index to cache.

    Args:
        player_id: NBA player ID
        player_name: Player name (for filename)
        data: Player data dictionary
        season: Season string (e.g., "2025-26")
    """
    players_dir = _get_players_dir(season)

    # Sanitize player name for filename
    safe_name = player_name.replace(" ", "_").replace(".", "")
    player_file = players_dir / f"{player_id}_{safe_name}.json"

    try:
        with open(player_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except IOError as e:
        print(f"Warning: Could not save player {player_name}: {e}")


def save_player_eligibility(player_id: int, eligible_positions: List[str],
                            season: str | None = None) -> None:
    """Save or update a player's eligible positions in their cached data.

    Args:
        player_id: NBA player ID
        eligible_positions: List of eligible position strings (e.g., ["PG", "SG"])
        season: Season string (e.g., "2025-26"). If provided, updates
                season-specific player data.
    """
    # Load existing player data
    player_data = load_player_games(player_id, season)

    if player_data is None:
        # Can't save eligibility without player name - skip
        return

    # Add eligible positions to player data
    player_data["eligible_positions"] = eligible_positions
    player_data["eligibility_updated"] = datetime.now().isoformat()

    # Save updated data
    player_name = player_data.get("player_name", f"Player_{player_id}")
    save_player_games(player_id, player_name, player_data, season)


def load_player_eligibility(player_id: int, season: str | None = None) -> Optional[List[str]]:
    """Load a player's eligible positions from cache.

    Args:
        player_id: NBA player ID
        season: Season string (e.g., "2025-26"). If provided, loads from
                season-specific player data.

    Returns:
        List of eligible position strings or None if not found
    """
    player_data = load_player_games(player_id, season)

    if player_data is None:
        return None

    return player_data.get("eligible_positions")


def get_cached_date_range(season: str | None = None) -> Tuple[Optional[date], Optional[date]]:
    """Get the date range of cached data.

    Args:
        season: Season string (e.g., "2025-26"). If provided, gets range
                from season-specific metadata. If None, uses legacy metadata.

    Returns:
        Tuple of (start_date, end_date) or (None, None) if no cache
    """
    metadata = load_metadata(season)
    date_range = metadata.get("date_range", {})

    start_str = date_range.get("start")
    end_str = date_range.get("end")

    if not start_str or not end_str:
        return (None, None)

    try:
        start = date.fromisoformat(start_str)
        end = date.fromisoformat(end_str)
        return (start, end)
    except (ValueError, TypeError):
        return (None, None)


def needs_refresh(season: str | None = None) -> bool:
    """Check if cache needs refresh based on last update time.

    Args:
        season: Season string (e.g., "2025-26"). If provided, checks
                season-specific metadata. If None, uses legacy metadata.

    Returns:
        True if cache should be refreshed
    """
    metadata = load_metadata(season)
    last_updated_str = metadata.get("last_updated")

    if not last_updated_str:
        return True

    try:
        last_updated = datetime.fromisoformat(last_updated_str)
        now = datetime.now()

        # Refresh if last update was more than 12 hours ago
        return (now - last_updated).total_seconds() > 43200
    except (ValueError, TypeError):
        return True


def update_player_index(
    player_id: int, player_name: str, game_data: dict, season: str
) -> None:
    """Incrementally update a player's game index with new game data.

    Args:
        player_id: NBA player ID
        player_name: Player name
        game_data: Game stats for this player
        season: Season (e.g., "2025-26")
    """
    # Load existing player data for this season
    player_data = load_player_games(player_id, season)

    if player_data is None:
        # Create new player data
        player_data = {
            "player_id": player_id,
            "player_name": player_name,
            "season": season,
            "last_updated": datetime.now().isoformat(),
            "games": [],
        }

    # Add new game (avoid duplicates)
    game_id = game_data.get("game_id")
    existing_game_ids = {g.get("game_id") for g in player_data.get("games", [])}

    if game_id not in existing_game_ids:
        player_data["games"].append(game_data)
        player_data["last_updated"] = datetime.now().isoformat()

        # Save updated player data for this season
        save_player_games(player_id, player_name, player_data, season)


def rebuild_player_index(player_id: int, season: str) -> Optional[dict]:
    """Rebuild a player's index by scanning all games in the season.

    Args:
        player_id: NBA player ID
        season: Season (e.g., "2025-26")

    Returns:
        Rebuilt player data or None if player not found
    """
    games_dir = _get_games_dir(season)
    player_games = []
    player_name = None

    # Scan all game files
    for game_file in sorted(games_dir.glob("*.json")):
        try:
            with open(game_file, "r") as f:
                game_data = json.load(f)

            box_score = game_data.get("box_score", {})
            player_stats = box_score.get(str(player_id))

            if player_stats:
                if not player_name:
                    player_name = player_stats.get("PLAYER_NAME", f"Player_{player_id}")

                # Build team tricode map for this game
                home_team_id = game_data.get("home_team")
                away_team_id = game_data.get("away_team")

                # Convert team IDs to int for comparison (they may be stored as strings)
                try:
                    home_team_id = int(home_team_id) if home_team_id else None
                    away_team_id = int(away_team_id) if away_team_id else None
                except (ValueError, TypeError):
                    home_team_id = None
                    away_team_id = None

                team_tricodes = {}
                for pid, pstats in box_score.items():
                    team_id = pstats.get("TEAM_ID")
                    if team_id and team_id not in team_tricodes:
                        team_tricodes[team_id] = pstats.get("teamTricode", "")

                home_tricode = team_tricodes.get(home_team_id, "")
                away_tricode = team_tricodes.get(away_team_id, "")

                # Construct MATCHUP field if not present
                player_team_id = player_stats.get("TEAM_ID")
                matchup = player_stats.get("MATCHUP", "")
                if not matchup and player_team_id and home_team_id and away_team_id:
                    if player_team_id == home_team_id and away_tricode:
                        matchup = f"vs {away_tricode}"
                    elif player_team_id == away_team_id and home_tricode:
                        matchup = f"@ {home_tricode}"

                game_entry = {
                    "date": game_data.get("game_date"),
                    "game_id": game_data.get("game_id"),
                    "home_score": game_data.get("home_score", 0),
                    "away_score": game_data.get("away_score", 0),
                    **{
                        k: v
                        for k, v in player_stats.items()
                        if k not in ["PLAYER_NAME", "PLAYER_ID"]
                    },
                }

                # Add or update MATCHUP field
                if matchup:
                    game_entry["MATCHUP"] = matchup

                player_games.append(game_entry)
        except (json.JSONDecodeError, IOError):
            continue

    if not player_games:
        return None

    player_data = {
        "player_id": player_id,
        "player_name": player_name or f"Player_{player_id}",
        "season": season,
        "last_updated": datetime.now().isoformat(),
        "games": player_games,
    }

    save_player_games(player_id, player_data["player_name"], player_data, season)
    return player_data


def rebuild_all_player_indexes(season: str) -> int:
    """Rebuild all player indexes by scanning all cached games.

    Args:
        season: Season (e.g., "2025-26")

    Returns:
        Number of players indexed
    """
    games_dir = _get_games_dir(season)
    player_data_map: Dict[int, dict] = {}

    # Scan all game files
    for game_file in sorted(games_dir.glob("*.json")):
        try:
            with open(game_file, "r", encoding="utf-8") as f:
                game_data = json.load(f)

            box_score = game_data.get("box_score", {})
            home_team_id = game_data.get("home_team")
            away_team_id = game_data.get("away_team")

            # Convert team IDs to int for comparison (they may be stored as strings)
            try:
                home_team_id = int(home_team_id) if home_team_id else None
                away_team_id = int(away_team_id) if away_team_id else None
            except (ValueError, TypeError):
                home_team_id = None
                away_team_id = None

            # Build team tricode map for this game
            team_tricodes = {}
            for pid, pstats in box_score.items():
                team_id = pstats.get("TEAM_ID")
                if team_id and team_id not in team_tricodes:
                    team_tricodes[team_id] = pstats.get("teamTricode", "")

            home_tricode = team_tricodes.get(home_team_id, "")
            away_tricode = team_tricodes.get(away_team_id, "")

            for player_id_str, player_stats in box_score.items():
                player_id = int(player_id_str)

                if player_id not in player_data_map:
                    player_name = player_stats.get("PLAYER_NAME", f"Player_{player_id}")
                    player_data_map[player_id] = {
                        "player_id": player_id,
                        "player_name": player_name,
                        "season": season,
                        "last_updated": datetime.now().isoformat(),
                        "games": [],
                    }

                # Construct MATCHUP field if not present
                player_team_id = player_stats.get("TEAM_ID")
                matchup = player_stats.get("MATCHUP", "")
                if not matchup and player_team_id and home_team_id and away_team_id:
                    if player_team_id == home_team_id and away_tricode:
                        matchup = f"vs {away_tricode}"
                    elif player_team_id == away_team_id and home_tricode:
                        matchup = f"@ {home_tricode}"

                game_entry = {
                    "date": game_data.get("game_date"),
                    "game_id": game_data.get("game_id"),
                    "home_score": game_data.get("home_score", 0),
                    "away_score": game_data.get("away_score", 0),
                    **{
                        k: v
                        for k, v in player_stats.items()
                        if k not in ["PLAYER_NAME", "PLAYER_ID"]
                    },
                }

                # Add or update MATCHUP field
                if matchup:
                    game_entry["MATCHUP"] = matchup

                player_data_map[player_id]["games"].append(game_entry)
        except (json.JSONDecodeError, IOError, ValueError):
            continue

    # Save all player indexes to season-specific directory
    for player_data in player_data_map.values():
        save_player_games(
            player_data["player_id"], player_data["player_name"], player_data, season
        )

    # Update season-specific metadata
    metadata = load_metadata(season)
    metadata["players_indexed"] = len(player_data_map)
    metadata["last_updated"] = datetime.now().isoformat()
    save_metadata(metadata, season)

    return len(player_data_map)


def backfill_team_scores(season: str) -> int:
    """Calculate and backfill team scores for all cached games.

    This reads existing boxscore data and calculates team scores by summing
    player PTS for each team. No API calls are made.

    Args:
        season: Season (e.g., "2025-26")

    Returns:
        Number of games updated with scores
    """
    games_dir = _get_games_dir(season)
    updated_count = 0

    for game_file in sorted(games_dir.glob("*.json")):
        try:
            with open(game_file, "r") as f:
                game_data = json.load(f)

            # Skip if already has scores
            if game_data.get("home_score") and game_data.get("away_score"):
                continue

            box_score = game_data.get("box_score", {})
            home_team = game_data.get("home_team")
            away_team = game_data.get("away_team")

            if not box_score or not home_team or not away_team:
                continue

            # Convert team IDs to comparable format
            try:
                home_team_id = int(home_team) if home_team else None
                away_team_id = int(away_team) if away_team else None
            except (ValueError, TypeError):
                continue

            # Calculate team scores by summing player PTS
            home_score = 0
            away_score = 0

            for player_stats in box_score.values():
                player_team_id = player_stats.get("TEAM_ID")
                pts = player_stats.get("PTS", 0)
                try:
                    pts = int(pts) if pts else 0
                except (ValueError, TypeError):
                    pts = 0

                if player_team_id == home_team_id:
                    home_score += pts
                elif player_team_id == away_team_id:
                    away_score += pts

            # Update game data with scores
            game_data["home_score"] = home_score
            game_data["away_score"] = away_score

            # Save updated game file
            with open(game_file, "w") as f:
                json.dump(game_data, f, indent=2)

            updated_count += 1

        except (json.JSONDecodeError, IOError):
            continue

    return updated_count


def backfill_scores_and_rebuild_indexes(season: str = "2025-26") -> dict:
    """Backfill team scores and rebuild player indexes.

    This is the main function to call to populate W/L and score data
    without making any API calls.

    Args:
        season: Season (e.g., "2025-26")

    Returns:
        Dictionary with counts of updated games and indexed players
    """
    print(f"Backfilling team scores for season {season}...")
    games_updated = backfill_team_scores(season)
    print(f"✓ Updated {games_updated} games with team scores")

    print("Rebuilding player indexes...")
    players_indexed = rebuild_all_player_indexes(season)
    print(f"✓ Rebuilt indexes for {players_indexed} players")

    return {
        "games_updated": games_updated,
        "players_indexed": players_indexed,
    }


def save_player_season_stats(
    player_id: int, player_name: str, season: str, stats: Dict
) -> None:
    """Save player season statistics.

    Args:
        player_id: NBA player ID
        player_name: Player name (for filename readability)
        season: Season string (e.g., "2025-26")
        stats: Dictionary of season averages
    """
    stats_dir = _get_season_stats_dir(season)
    # Sanitize player name for filename
    safe_name = player_name.replace(" ", "_").replace("/", "_").replace(".", "")
    stats_file = stats_dir / f"{player_id}_{safe_name}.json"

    data = {
        "player_id": player_id,
        "player_name": player_name,
        "season": season,
        "stats": stats,
        "last_updated": datetime.now().isoformat(),
    }

    with open(stats_file, "w") as f:
        json.dump(data, f, indent=2)


def load_player_season_stats(player_id: int, season: str) -> Optional[Dict]:
    """Load player season statistics from cache.

    Args:
        player_id: NBA player ID
        season: Season string (e.g., "2025-26")

    Returns:
        Dictionary of season stats, or None if not cached
    """
    stats_dir = _get_season_stats_dir(season)

    # Find file by player_id prefix
    for stats_file in stats_dir.glob(f"{player_id}_*.json"):
        try:
            with open(stats_file, "r") as f:
                data = json.load(f)
                return data.get("stats")
        except (json.JSONDecodeError, IOError):
            continue

    return None


def compute_and_save_all_season_stats(season: str) -> int:
    """Compute season averages for all players from cached games and save them.

    Args:
        season: Season string (e.g., "2025-26")

    Returns:
        Number of players processed
    """
    # Use season-specific players directory
    players_dir = _get_players_dir(season)
    count = 0

    for player_file in players_dir.glob("*.json"):
        try:
            with open(player_file, "r") as f:
                player_data = json.load(f)

            player_id = player_data.get("player_id")
            player_name = player_data.get("player_name", "Unknown")
            games = player_data.get("games", [])

            if not games:
                continue

            # Compute season averages
            total_fgm = sum(float(g.get("FGM", 0)) for g in games)
            total_fga = sum(float(g.get("FGA", 0)) for g in games)
            total_ftm = sum(float(g.get("FTM", 0)) for g in games)
            total_fta = sum(float(g.get("FTA", 0)) for g in games)
            total_3pm = sum(float(g.get("FG3M", 0)) for g in games)
            total_pts = sum(float(g.get("PTS", 0)) for g in games)
            total_reb = sum(float(g.get("REB", 0)) for g in games)
            total_ast = sum(float(g.get("AST", 0)) for g in games)
            total_stl = sum(float(g.get("STL", 0)) for g in games)
            total_blk = sum(float(g.get("BLK", 0)) for g in games)
            total_to = sum(float(g.get("TO", 0)) for g in games)

            num_games = len(games)

            season_stats = {
                "games_played": num_games,
                # Per-game averages
                "fgm": total_fgm / num_games if num_games > 0 else 0,
                "fga": total_fga / num_games if num_games > 0 else 0,
                "fg_pct": total_fgm / total_fga if total_fga > 0 else 0,
                "ftm": total_ftm / num_games if num_games > 0 else 0,
                "fta": total_fta / num_games if num_games > 0 else 0,
                "ft_pct": total_ftm / total_fta if total_fta > 0 else 0,
                "threes": total_3pm / num_games if num_games > 0 else 0,
                "points": total_pts / num_games if num_games > 0 else 0,
                "rebounds": total_reb / num_games if num_games > 0 else 0,
                "assists": total_ast / num_games if num_games > 0 else 0,
                "steals": total_stl / num_games if num_games > 0 else 0,
                "blocks": total_blk / num_games if num_games > 0 else 0,
                "turnovers": total_to / num_games if num_games > 0 else 0,
            }

            save_player_season_stats(player_id, player_name, season, season_stats)
            count += 1

        except (json.JSONDecodeError, IOError, ValueError, KeyError):
            continue

    return count


def _game_finished_buffer_passed(game_datetime_str: str, hours: int = 5) -> bool:
    """Check if enough time has passed since game start for it to be finished.

    Games typically last 2-3 hours, so we add a buffer to avoid flagging
    games as "missing" while they're still in progress.

    Args:
        game_datetime_str: Game start time in ISO format (ET timezone).
            Format: "2025-11-19T19:00:00Z" (Z is misleading - it's actually ET)
        hours: Number of hours after game start to consider it finished.
            Default 5 hours gives ample time for game completion.

    Returns:
        True if current time > game_datetime + hours (game should be finished)
        True if parsing fails (conservative - assume should be cached)
        False if game may still be in progress
    """
    if not game_datetime_str:
        # No time info, assume it should be cached (conservative)
        return True

    try:
        import pytz

        eastern = pytz.timezone("US/Eastern")

        # Handle the timestamp format from NBA API
        # gameDateTimeEst format: "2025-11-19T19:00:00Z" (Z is misleading - it's actually ET)
        if "T" in game_datetime_str:
            # Remove the 'Z' suffix and parse as naive datetime
            clean_time_str = game_datetime_str.replace("Z", "")
            game_time_naive = datetime.fromisoformat(clean_time_str)
            # Localize to Eastern Time (the API gives us Eastern Time despite the Z suffix)
            game_time = eastern.localize(game_time_naive)
        else:
            # No time component, assume midnight Eastern
            game_time = eastern.localize(
                datetime.strptime(game_datetime_str, "%Y-%m-%d")
            )

        # Get current time in Eastern
        now_eastern = datetime.now(eastern)

        # Calculate time since game started
        time_since_game = (now_eastern - game_time).total_seconds()
        buffer_seconds = hours * 3600

        # Return True if enough time has passed
        return time_since_game >= buffer_seconds

    except (ValueError, TypeError, ImportError):
        # If we can't parse the time, assume it should be cached (conservative)
        return True


def detect_missing_games(
    season: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> Dict[str, dict]:
    """Detect missing boxscores by comparing schedule vs cached data.

    Compares the NBA schedule against cached boxscore files to identify
    games that should have been played but are missing from the cache.

    Args:
        season: Season string (e.g., "2025-26")
        start_date: Start of date range to check. If None, uses season start.
        end_date: End of date range to check. If None, uses yesterday.

    Returns:
        Dictionary mapping dates to detection results:
        {
            "2024-11-27": {
                "expected": 9,
                "cached": 7,
                "missing": [
                    {
                        "game_id": "0022400123",
                        "home_team": "Lakers",
                        "away_team": "Celtics",
                        "home_team_tricode": "LAL",
                        "away_team_tricode": "BOS",
                    },
                    ...
                ],
                "missing_count": 2
            },
            ...
        }
    """
    from datetime import timedelta

    from tools.schedule import schedule_cache

    # Load full schedule
    schedule_data = schedule_cache.load_full_schedule(season)
    if not schedule_data:
        return {}

    date_games = schedule_data.get("date_games", {})

    # Determine date range
    if start_date is None:
        # Use season start
        try:
            year = int(season.split("-")[0])
            start_date = date(year, 10, 21)  # NBA season typically starts Oct 21
        except (ValueError, IndexError):
            start_date = date.today() - timedelta(days=30)

    if end_date is None:
        # Use yesterday (today's games may still be in progress)
        end_date = date.today() - timedelta(days=1)

    # Get games directory for this season
    games_dir = _get_games_dir(season)

    # Scan cached game files once and build a set of cached game IDs
    cached_game_ids = set()
    for game_file in games_dir.glob("*.json"):
        # File format: YYYYMMDD_gameid.json
        try:
            parts = game_file.stem.split("_")
            if len(parts) >= 2:
                game_id = parts[1]
                cached_game_ids.add(game_id)
        except (IndexError, ValueError):
            continue

    # Compare schedule vs cache for each date
    results = {}
    current_date = start_date

    while current_date <= end_date:
        date_str = current_date.isoformat()
        scheduled_games = date_games.get(date_str, [])

        if not scheduled_games:
            current_date += timedelta(days=1)
            continue

        # Find missing games for this date
        missing_games = []
        cached_count = 0

        for game in scheduled_games:
            game_id = str(game.get("game_id", ""))

            # Skip postponed games - they will never have box scores
            if game.get("postponed_status") == "Y":
                continue

            if game_id in cached_game_ids:
                cached_count += 1
            else:
                # Check if enough time has passed since game start (5 hours)
                # Games may still be in progress if started recently
                game_time_str = game.get("game_datetime", "")
                if not _game_finished_buffer_passed(game_time_str, hours=5):
                    # Game may still be in progress, don't count as missing
                    continue

                # This game is missing from cache
                missing_games.append({
                    "game_id": game_id,
                    "home_team": game.get("home_team_name", ""),
                    "away_team": game.get("away_team_name", ""),
                    "home_team_tricode": game.get("home_team_tricode", ""),
                    "away_team_tricode": game.get("away_team_tricode", ""),
                    "game_datetime": game.get("game_datetime", ""),
                })

        # Only include dates with missing games
        if missing_games:
            results[date_str] = {
                "expected": len(scheduled_games),
                "cached": cached_count,
                "missing": missing_games,
                "missing_count": len(missing_games),
            }

        current_date += timedelta(days=1)

    return results


def get_missing_games_summary(season: str) -> Dict:
    """Get a summary of missing games across all dates.

    Args:
        season: Season string (e.g., "2025-26")

    Returns:
        Summary dictionary with total counts and by-date breakdown
    """
    missing_by_date = detect_missing_games(season)

    total_missing = 0
    total_expected = 0
    total_cached = 0
    dates_with_missing = 0

    for date_str, info in missing_by_date.items():
        total_missing += info["missing_count"]
        total_expected += info["expected"]
        total_cached += info["cached"]
        dates_with_missing += 1

    return {
        "total_missing": total_missing,
        "total_expected": total_expected,
        "total_cached": total_cached,
        "dates_with_missing": dates_with_missing,
        "by_date": missing_by_date,
    }
