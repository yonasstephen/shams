"""Tests for the extension feed builder's player file."""

from __future__ import annotations

from datetime import date

import pytest

from scripts.build_feed import build_players
from tools.boxscore import boxscore_cache


@pytest.fixture(name="cached_player")
def fixture_cached_player(temp_cache_dir, sample_player_games, monkeypatch):
    """Three cached games, on 2024-10-25, 10-27 and 10-29."""
    monkeypatch.setattr(boxscore_cache, "get_cache_dir", lambda: temp_cache_dir)
    boxscore_cache.save_player_games(
        sample_player_games["player_id"],
        sample_player_games["player_name"],
        sample_player_games,
        sample_player_games["season"],
    )
    # A stale whole-season average on disk, as the refresh leaves it: the feed must not use it.
    boxscore_cache.compute_and_save_all_season_stats(sample_player_games["season"])
    return sample_player_games


@pytest.mark.unit
def test_historical_feed_sees_only_games_up_to_its_anchor(cached_player):
    """A feed anchored mid-season must not average in games played after that day."""
    players = build_players(cached_player["season"], tail_days=35, today=date(2024, 10, 27))
    entry = players["players"][str(cached_player["player_id"])]

    assert [row[0] for row in entry["games"]] == ["2024-10-25", "2024-10-27"]
    season = entry["season_avg"]
    assert season["games_played"] == 2
    assert season["points"] == pytest.approx((26 + 40) / 2)
    assert season["fg_pct"] == pytest.approx((10 + 14) / (18 + 22), abs=1e-4)
    assert season["mpg"] == pytest.approx((34 + 36.5) / 2)


@pytest.mark.unit
def test_current_feed_matches_the_cached_season_average(cached_player):
    """Anchored after the last game, the feed carries the same averages the cache saved."""
    players = build_players(cached_player["season"], tail_days=35, today=date(2024, 11, 1))
    season = players["players"][str(cached_player["player_id"])]["season_avg"]
    saved = boxscore_cache.load_player_season_stats(cached_player["player_id"], cached_player["season"])

    assert season["games_played"] == 3
    for field in ("fgm", "fga", "fg_pct", "ftm", "fta", "ft_pct", "threes", "points", "turnovers"):
        assert season[field] == pytest.approx(saved[field], abs=1e-4), field
    assert season["mpg"] == pytest.approx((34 + 36.5 + 32) / 3, abs=0.01)


@pytest.mark.unit
def test_player_without_games_by_the_anchor_is_left_out(cached_player):
    """Someone whose first game comes after the anchor has no season yet."""
    players = build_players(cached_player["season"], tail_days=35, today=date(2024, 10, 20))
    assert players["count"] == 0
    assert not players["players"]
