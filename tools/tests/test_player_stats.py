"""Tests for player stats computation."""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import Mock, patch

import pytest

from tools.player import player_stats


@pytest.mark.unit
def test_parse_stat_mode_last():
    """Test parsing 'last' mode."""
    num_games, num_days = player_stats._parse_stat_mode("last")
    assert num_games == 1
    assert num_days is None


@pytest.mark.unit
def test_parse_stat_mode_season():
    """Test parsing 'season' mode."""
    num_games, num_days = player_stats._parse_stat_mode("season")
    assert num_games is None
    assert num_days is None


@pytest.mark.unit
def test_parse_stat_mode_last_n_games():
    """Test parsing 'lastN' mode for games."""
    num_games, num_days = player_stats._parse_stat_mode("last7")
    assert num_games == 7
    assert num_days is None

    num_games, num_days = player_stats._parse_stat_mode("last10")
    assert num_games == 10
    assert num_days is None


@pytest.mark.unit
def test_parse_stat_mode_last_n_days():
    """Test parsing 'lastNd' mode for days."""
    num_games, num_days = player_stats._parse_stat_mode("last7d")
    assert num_games is None
    assert num_days == 7

    num_games, num_days = player_stats._parse_stat_mode("last14d")
    assert num_games is None
    assert num_days == 14


@pytest.mark.unit
def test_parse_stat_mode_invalid():
    """Test parsing invalid mode defaults to 'last'."""
    num_games, num_days = player_stats._parse_stat_mode("invalid")
    assert num_games == 1
    assert num_days is None


@pytest.mark.unit
@patch("tools.player.player_fetcher.fetch_player_stats_from_cache")
def test_compute_player_stats_last_game(mock_fetch):
    """Test computing stats for last game only."""
    mock_fetch.return_value = [
        {
            "date": "2024-11-01",
            "FGM": 12,
            "FGA": 20,
            "FTM": 8,
            "FTA": 12,
            "FG3M": 1,
            "PTS": 33,
            "REB": 11,
            "AST": 7,
            "STL": 2,
            "BLK": 3,
            "TO": 4,
            "USG_PCT": 0.35,
            "PLUS_MINUS": 12,
            "IS_STARTER": 1,
            "MIN": 36.5,
        },
        {
            "date": "2024-10-30",
            "FGM": 10,
            "FGA": 18,
            "FTM": 6,
            "FTA": 8,
            "FG3M": 0,
            "PTS": 26,
            "REB": 12,
            "AST": 6,
            "STL": 1,
            "BLK": 2,
            "TO": 3,
            "USG_PCT": 0.32,
            "PLUS_MINUS": 8,
            "IS_STARTER": 1,
            "MIN": 34.0,
        },
    ]

    player_id = 203507
    season_start = date(2024, 10, 1)
    today = date(2024, 11, 1)

    stats = player_stats.compute_player_stats(
        player_id, "last", season_start, today, agg_mode="avg"
    )

    assert stats is not None
    assert stats.games_count == 1
    assert stats.points == 33  # Most recent game
    assert stats.rebounds == 11
    assert stats.assists == 7
    assert abs(stats.fg_pct - 0.6) < 0.01  # 12/20
    assert abs(stats.ft_pct - 0.667) < 0.01  # 8/12
    assert stats.minutes == 36.5  # Most recent game minutes


@pytest.mark.unit
@patch("tools.player.player_fetcher.fetch_player_stats_from_cache")
def test_compute_player_stats_last_n_games(mock_fetch):
    """Test computing stats for last N games."""
    mock_fetch.return_value = [
        {
            "date": "2024-11-01",
            "FGM": 12,
            "FGA": 20,
            "FTM": 8,
            "FTA": 12,
            "FG3M": 1,
            "PTS": 33,
            "REB": 11,
            "AST": 7,
            "STL": 2,
            "BLK": 3,
            "TO": 4,
            "USG_PCT": 0.35,
            "PLUS_MINUS": 12,
            "IS_STARTER": 1,
            "MIN": 36.5,
        },
        {
            "date": "2024-10-30",
            "FGM": 10,
            "FGA": 18,
            "FTM": 6,
            "FTA": 8,
            "FG3M": 0,
            "PTS": 26,
            "REB": 12,
            "AST": 6,
            "STL": 1,
            "BLK": 2,
            "TO": 3,
            "USG_PCT": 0.32,
            "PLUS_MINUS": 8,
            "IS_STARTER": 1,
            "MIN": 34.0,
        },
        {
            "date": "2024-10-28",
            "FGM": 8,
            "FGA": 16,
            "FTM": 5,
            "FTA": 6,
            "FG3M": 1,
            "PTS": 22,
            "REB": 10,
            "AST": 5,
            "STL": 1,
            "BLK": 1,
            "TO": 2,
            "USG_PCT": 0.28,
            "PLUS_MINUS": 5,
            "IS_STARTER": 1,
            "MIN": 32.0,
        },
    ]

    player_id = 203507
    season_start = date(2024, 10, 1)
    today = date(2024, 11, 1)

    stats = player_stats.compute_player_stats(
        player_id, "last3", season_start, today, agg_mode="avg"
    )

    assert stats is not None
    assert stats.games_count == 3
    # Average: (33 + 26 + 22) / 3 = 27
    assert abs(stats.points - 27.0) < 0.1
    # Average: (11 + 12 + 10) / 3 = 11
    assert abs(stats.rebounds - 11.0) < 0.1
    # FG%: (12+10+8) / (20+18+16) = 30/54 = 0.556
    assert abs(stats.fg_pct - 0.556) < 0.01
    # Average minutes: (36.5 + 34.0 + 32.0) / 3 = 34.17
    assert abs(stats.minutes - 34.17) < 0.1


@pytest.mark.unit
@patch("tools.player.player_fetcher.fetch_player_stats_from_cache")
def test_compute_player_stats_sum_mode(mock_fetch):
    """Test computing total stats (sum mode)."""
    mock_fetch.return_value = [
        {
            "date": "2024-11-01",
            "FGM": 12,
            "FGA": 20,
            "FTM": 8,
            "FTA": 12,
            "FG3M": 1,
            "PTS": 33,
            "REB": 11,
            "AST": 7,
            "STL": 2,
            "BLK": 3,
            "TO": 4,
            "USG_PCT": 0.35,
            "PLUS_MINUS": 12,
            "IS_STARTER": 1,
            "MIN": 36.5,
        },
        {
            "date": "2024-10-30",
            "FGM": 10,
            "FGA": 18,
            "FTM": 6,
            "FTA": 8,
            "FG3M": 0,
            "PTS": 26,
            "REB": 12,
            "AST": 6,
            "STL": 1,
            "BLK": 2,
            "TO": 3,
            "USG_PCT": 0.32,
            "PLUS_MINUS": 8,
            "IS_STARTER": 1,
            "MIN": 34.0,
        },
    ]

    player_id = 203507
    season_start = date(2024, 10, 1)
    today = date(2024, 11, 1)

    stats = player_stats.compute_player_stats(
        player_id, "last2", season_start, today, agg_mode="sum"
    )

    assert stats is not None
    assert stats.games_count == 2
    # Total points: 33 + 26 = 59
    assert stats.points == 59
    # Total rebounds: 11 + 12 = 23
    assert stats.rebounds == 23
    # FG% is still calculated as percentage (not summed)
    assert abs(stats.fg_pct - 0.579) < 0.01  # (12+10)/(20+18)
    # Total minutes: 36.5 + 34.0 = 70.5
    assert abs(stats.minutes - 70.5) < 0.1


@pytest.mark.unit
@patch("tools.player.player_fetcher.fetch_player_stats_from_cache")
def test_compute_player_stats_last_n_days(mock_fetch):
    """Test computing stats for last N days."""
    today = date(2024, 11, 5)
    mock_fetch.return_value = [
        {
            "date": "2024-11-05",
            "FGM": 12,
            "FGA": 20,
            "FTM": 8,
            "FTA": 12,
            "FG3M": 1,
            "PTS": 33,
            "REB": 11,
            "AST": 7,
            "STL": 2,
            "BLK": 3,
            "TO": 4,
            "USG_PCT": 0.35,
            "PLUS_MINUS": 12,
            "IS_STARTER": 1,
            "MIN": 36.5,
        },
        {
            "date": "2024-11-03",
            "FGM": 10,
            "FGA": 18,
            "FTM": 6,
            "FTA": 8,
            "FG3M": 0,
            "PTS": 26,
            "REB": 12,
            "AST": 6,
            "STL": 1,
            "BLK": 2,
            "TO": 3,
            "USG_PCT": 0.32,
            "PLUS_MINUS": 8,
            "IS_STARTER": 1,
            "MIN": 34.0,
        },
        {
            "date": "2024-10-28",
            "FGM": 8,
            "FGA": 16,
            "FTM": 5,
            "FTA": 6,
            "FG3M": 1,
            "PTS": 22,
            "REB": 10,
            "AST": 5,
            "STL": 1,
            "BLK": 1,
            "TO": 2,
            "USG_PCT": 0.28,
            "PLUS_MINUS": 5,
            "IS_STARTER": 1,
            "MIN": 32.0,
        },
    ]

    player_id = 203507
    season_start = date(2024, 10, 1)

    # Last 7 days should include games from 2024-10-29 onwards
    stats = player_stats.compute_player_stats(
        player_id, "last7d", season_start, today, agg_mode="avg"
    )

    assert stats is not None
    assert stats.games_count == 2  # Only 2 games in last 7 days
    # Average: (33 + 26) / 2 = 29.5
    assert abs(stats.points - 29.5) < 0.1


@pytest.mark.unit
@patch("tools.player.player_fetcher.fetch_player_stats_from_cache")
def test_compute_player_stats_no_games(mock_fetch):
    """Test when player has no games."""
    mock_fetch.return_value = []

    player_id = 203507
    season_start = date(2024, 10, 1)
    today = date(2024, 11, 1)

    stats = player_stats.compute_player_stats(player_id, "last", season_start, today)

    assert stats is None


@pytest.mark.unit
def test_sort_by_column_points_desc():
    """Test sorting players by points (descending by default)."""
    from tools.player.player_stats import PlayerStats

    stats1 = PlayerStats(
        fg_pct=0.5,
        ft_pct=0.8,
        threes=2.0,
        points=25.0,
        rebounds=8.0,
        assists=5.0,
        steals=1.0,
        blocks=1.0,
        turnovers=2.0,
        games_count=10,
        fgm=10.0,
        fga=20.0,
        ftm=8.0,
        fta=10.0,
        usage_pct=0.3,
        games_started=10,
        plus_minus=5.0,
        minutes=32.0,
    )
    stats2 = PlayerStats(
        fg_pct=0.55,
        ft_pct=0.85,
        threes=3.0,
        points=30.0,
        rebounds=10.0,
        assists=7.0,
        steals=2.0,
        blocks=2.0,
        turnovers=3.0,
        games_count=10,
        fgm=11.0,
        fga=20.0,
        ftm=9.0,
        fta=10.0,
        usage_pct=0.35,
        games_started=10,
        plus_minus=8.0,
        minutes=35.0,
    )

    players = [
        {"name": "Player A", "stats": stats1},
        {"name": "Player B", "stats": stats2},
    ]

    sorted_players = player_stats.sort_by_column(players, "PTS")

    assert sorted_players[0]["name"] == "Player B"  # Higher points first
    assert sorted_players[1]["name"] == "Player A"


@pytest.mark.unit
def test_sort_by_column_turnovers_asc():
    """Test sorting players by turnovers (ascending by default - lower is better)."""
    from tools.player.player_stats import PlayerStats

    stats1 = PlayerStats(
        fg_pct=0.5,
        ft_pct=0.8,
        threes=2.0,
        points=25.0,
        rebounds=8.0,
        assists=5.0,
        steals=1.0,
        blocks=1.0,
        turnovers=4.0,
        games_count=10,
        fgm=10.0,
        fga=20.0,
        ftm=8.0,
        fta=10.0,
        usage_pct=0.3,
        games_started=10,
        plus_minus=5.0,
        minutes=32.0,
    )
    stats2 = PlayerStats(
        fg_pct=0.55,
        ft_pct=0.85,
        threes=3.0,
        points=30.0,
        rebounds=10.0,
        assists=7.0,
        steals=2.0,
        blocks=2.0,
        turnovers=2.0,
        games_count=10,
        fgm=11.0,
        fga=20.0,
        ftm=9.0,
        fta=10.0,
        usage_pct=0.35,
        games_started=10,
        plus_minus=8.0,
        minutes=35.0,
    )

    players = [
        {"name": "Player A", "stats": stats1},
        {"name": "Player B", "stats": stats2},
    ]

    sorted_players = player_stats.sort_by_column(players, "TO")

    assert sorted_players[0]["name"] == "Player B"  # Lower turnovers first
    assert sorted_players[1]["name"] == "Player A"


@pytest.mark.unit
def test_sort_by_column_explicit_order():
    """Test sorting with explicit ascending/descending order."""
    from tools.player.player_stats import PlayerStats

    stats1 = PlayerStats(
        fg_pct=0.5,
        ft_pct=0.8,
        threes=2.0,
        points=25.0,
        rebounds=8.0,
        assists=5.0,
        steals=1.0,
        blocks=1.0,
        turnovers=2.0,
        games_count=10,
        fgm=10.0,
        fga=20.0,
        ftm=8.0,
        fta=10.0,
        usage_pct=0.3,
        games_started=10,
        plus_minus=5.0,
        minutes=32.0,
    )
    stats2 = PlayerStats(
        fg_pct=0.55,
        ft_pct=0.85,
        threes=3.0,
        points=30.0,
        rebounds=10.0,
        assists=7.0,
        steals=2.0,
        blocks=2.0,
        turnovers=3.0,
        games_count=10,
        fgm=11.0,
        fga=20.0,
        ftm=9.0,
        fta=10.0,
        usage_pct=0.35,
        games_started=10,
        plus_minus=8.0,
        minutes=35.0,
    )

    players = [
        {"name": "Player A", "stats": stats1},
        {"name": "Player B", "stats": stats2},
    ]

    # Sort turnovers descending (force opposite of default)
    sorted_players = player_stats.sort_by_column(players, "TO", ascending=False)

    assert (
        sorted_players[0]["name"] == "Player B"
    )  # Higher turnovers first when descending
    assert sorted_players[1]["name"] == "Player A"
