"""Tests for boxscore cache operations."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from tools.boxscore import boxscore_cache


@pytest.mark.unit
def test_save_and_load_game(temp_cache_dir, sample_game_data, monkeypatch):
    """Test saving and loading a game from cache."""
    monkeypatch.setattr(boxscore_cache, "get_cache_dir", lambda: temp_cache_dir)

    game_id = sample_game_data["game_id"]
    season = "2024-25"
    game_date = sample_game_data["game_date"]

    # Save game
    boxscore_cache.save_game(game_id, season, game_date, sample_game_data)

    # Load game
    loaded_game = boxscore_cache.load_game(game_id, season)

    assert loaded_game is not None
    assert loaded_game["game_id"] == game_id
    assert loaded_game["game_date"] == game_date
    assert "203507" in loaded_game["box_score"]


@pytest.mark.unit
def test_load_nonexistent_game(temp_cache_dir, monkeypatch):
    """Test loading a game that doesn't exist."""
    monkeypatch.setattr(boxscore_cache, "get_cache_dir", lambda: temp_cache_dir)

    loaded_game = boxscore_cache.load_game("nonexistent", "2024-25")
    assert loaded_game is None


@pytest.mark.unit
def test_save_and_load_player_games(temp_cache_dir, sample_player_games, monkeypatch):
    """Test saving and loading player games."""
    monkeypatch.setattr(boxscore_cache, "get_cache_dir", lambda: temp_cache_dir)

    player_id = sample_player_games["player_id"]
    player_name = sample_player_games["player_name"]

    # Save player games
    boxscore_cache.save_player_games(player_id, player_name, sample_player_games, "2025-26")

    # Load player games
    loaded_player = boxscore_cache.load_player_games(player_id, "2025-26")

    assert loaded_player is not None
    assert loaded_player["player_id"] == player_id
    assert loaded_player["player_name"] == player_name
    assert len(loaded_player["games"]) == 3


@pytest.mark.unit
def test_get_cached_date_range(temp_cache_dir, monkeypatch):
    """Test getting cached date range from metadata."""
    monkeypatch.setattr(boxscore_cache, "get_cache_dir", lambda: temp_cache_dir)

    # Save metadata with date range
    metadata = {
        "season": "2024-25",
        "games_cached": 50,
        "players_indexed": 200,
        "date_range": {"start": "2024-10-25", "end": "2024-11-01"},
    }
    boxscore_cache.save_metadata(metadata)

    # Get date range
    start, end = boxscore_cache.get_cached_date_range()

    assert start == date(2024, 10, 25)
    assert end == date(2024, 11, 1)


@pytest.mark.unit
def test_get_cached_date_range_no_cache(temp_cache_dir, monkeypatch):
    """Test getting date range when no cache exists."""
    monkeypatch.setattr(boxscore_cache, "get_cache_dir", lambda: temp_cache_dir)

    start, end = boxscore_cache.get_cached_date_range()

    assert start is None
    assert end is None


@pytest.mark.unit
def test_compute_and_save_all_season_stats(
    temp_cache_dir, sample_player_games, monkeypatch
):
    """Test computing and saving season stats for all players."""
    monkeypatch.setattr(boxscore_cache, "get_cache_dir", lambda: temp_cache_dir)

    # Save a player's games to season-specific directory
    player_id = sample_player_games["player_id"]
    player_name = sample_player_games["player_name"]
    season = sample_player_games["season"]
    boxscore_cache.save_player_games(player_id, player_name, sample_player_games, season)

    # Compute stats
    count = boxscore_cache.compute_and_save_all_season_stats(season)

    assert count == 1

    # Load computed stats
    stats = boxscore_cache.load_player_season_stats(player_id, season)

    assert stats is not None
    assert stats["games_played"] == 3
    assert "fg_pct" in stats
    assert "points" in stats
    # Verify averages are computed correctly
    # Player had 26, 40, 22 points = 88 total / 3 games = 29.33 avg
    assert abs(stats["points"] - 29.33) < 0.1


@pytest.mark.unit
def test_rebuild_all_player_indexes(temp_cache_dir, sample_game_data, monkeypatch):
    """Test rebuilding all player indexes from cached games."""
    monkeypatch.setattr(boxscore_cache, "get_cache_dir", lambda: temp_cache_dir)

    season = "2024-25"
    game_date = sample_game_data["game_date"]
    game_id = sample_game_data["game_id"]

    # Save a game
    boxscore_cache.save_game(game_id, season, game_date, sample_game_data)

    # Rebuild player indexes
    count = boxscore_cache.rebuild_all_player_indexes(season)

    assert count == 2  # Two players in the sample game

    # Check that player data was created (use season-specific directory)
    giannis_data = boxscore_cache.load_player_games(203507, season)
    assert giannis_data is not None
    assert giannis_data["player_name"] == "Giannis Antetokounmpo"
    assert len(giannis_data["games"]) == 1


@pytest.mark.unit
def test_update_player_index(temp_cache_dir, monkeypatch):
    """Test incrementally updating a player's game index."""
    monkeypatch.setattr(boxscore_cache, "get_cache_dir", lambda: temp_cache_dir)

    player_id = 203507
    player_name = "Giannis Antetokounmpo"
    season = "2024-25"

    game_data_1 = {"game_id": "0022300001", "date": "2024-10-25", "PTS": 26, "REB": 12}

    game_data_2 = {"game_id": "0022300002", "date": "2024-10-27", "PTS": 30, "REB": 10}

    # Add first game
    boxscore_cache.update_player_index(player_id, player_name, game_data_1, season)

    player_data = boxscore_cache.load_player_games(player_id, season)
    assert len(player_data["games"]) == 1

    # Add second game
    boxscore_cache.update_player_index(player_id, player_name, game_data_2, season)

    player_data = boxscore_cache.load_player_games(player_id, season)
    assert len(player_data["games"]) == 2

    # Try adding duplicate (should not create duplicate)
    boxscore_cache.update_player_index(player_id, player_name, game_data_1, season)

    player_data = boxscore_cache.load_player_games(player_id, season)
    assert len(player_data["games"]) == 2  # Still only 2 games


@pytest.mark.unit
def test_clear_cache(temp_cache_dir, sample_game_data, monkeypatch):
    """Test clearing the cache."""
    monkeypatch.setattr(boxscore_cache, "get_cache_dir", lambda: temp_cache_dir)

    # Create some cached data
    boxscore_cache.save_game("test_game", "2024-25", "2024-11-01", sample_game_data)
    boxscore_cache.save_metadata({"test": "data"})

    # Verify data exists
    assert (temp_cache_dir / "games").exists()
    assert (temp_cache_dir / "metadata.json").exists()

    # Clear cache
    boxscore_cache.clear_cache()

    # Verify data is gone
    assert not (temp_cache_dir / "games").exists()
    assert not (temp_cache_dir / "metadata.json").exists()


@pytest.mark.unit
def test_needs_refresh_no_metadata(temp_cache_dir, monkeypatch):
    """Test needs_refresh when no metadata exists."""
    monkeypatch.setattr(boxscore_cache, "get_cache_dir", lambda: temp_cache_dir)

    assert boxscore_cache.needs_refresh() is True


@pytest.mark.unit
def test_needs_refresh_old_data(temp_cache_dir, monkeypatch):
    """Test needs_refresh when data is old."""
    monkeypatch.setattr(boxscore_cache, "get_cache_dir", lambda: temp_cache_dir)

    # Save metadata with old timestamp (more than 12 hours ago)
    from datetime import timedelta
    old_time = datetime.now() - timedelta(hours=13)  # 13 hours ago, > 12 hour threshold
    metadata = {"last_updated": old_time.isoformat()}
    boxscore_cache.save_metadata(metadata)

    assert boxscore_cache.needs_refresh() is True


@pytest.mark.unit
def test_needs_refresh_recent_data(temp_cache_dir, monkeypatch):
    """Test needs_refresh when data is recent."""
    monkeypatch.setattr(boxscore_cache, "get_cache_dir", lambda: temp_cache_dir)

    # Save metadata with recent timestamp
    metadata = {"last_updated": datetime.now().isoformat()}
    boxscore_cache.save_metadata(metadata)

    assert boxscore_cache.needs_refresh() is False


@pytest.mark.unit
def test_metadata_end_date_reflects_actual_data(
    temp_cache_dir, sample_game_data, monkeypatch
):
    """Test that metadata end date reflects actual boxscore data, not requested end date."""
    monkeypatch.setattr(boxscore_cache, "get_cache_dir", lambda: temp_cache_dir)

    season = "2024-25"

    # Save a game for 2024-11-19
    game_date_1 = "2024-11-19"
    boxscore_cache.save_game("game1", season, game_date_1, sample_game_data)

    # Update metadata as if we requested data through 2024-11-20 but only got data for 2024-11-19
    metadata = boxscore_cache.load_metadata()
    metadata["season"] = season
    metadata["games_cached"] = 1
    metadata["date_range"] = {
        "start": game_date_1,
        "end": game_date_1,  # Should reflect actual last data, not requested end (2024-11-20)
    }
    boxscore_cache.save_metadata(metadata)

    # Verify the end date is 2024-11-19, not 2024-11-20
    start, end = boxscore_cache.get_cached_date_range()
    assert end == date(
        2024, 11, 19
    ), "End date should reflect last date with actual data"
