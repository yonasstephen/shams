"""Pytest configuration and fixtures for tools tests."""

from __future__ import annotations

import json
import tempfile
from datetime import date
from pathlib import Path
from typing import Dict

import pytest


@pytest.fixture
def temp_cache_dir(tmp_path):
    """Create a temporary cache directory for testing."""
    cache_dir = tmp_path / "test_cache"
    cache_dir.mkdir()
    return cache_dir


@pytest.fixture
def sample_game_data() -> Dict:
    """Sample game data for testing."""
    return {
        "game_id": "0022300123",
        "game_date": "2024-11-01",
        "home_team": "1610612747",
        "away_team": "1610612738",
        "box_score": {
            "203507": {  # Giannis Antetokounmpo
                "PLAYER_ID": 203507,
                "PLAYER_NAME": "Giannis Antetokounmpo",
                "TEAM_ID": 1610612749,
                "MIN": "35:24",
                "FGM": 12,
                "FGA": 20,
                "FG_PCT": 0.600,
                "FG3M": 1,
                "FG3A": 3,
                "FG3_PCT": 0.333,
                "FTM": 8,
                "FTA": 12,
                "FT_PCT": 0.667,
                "OREB": 2,
                "DREB": 9,
                "REB": 11,
                "AST": 7,
                "STL": 2,
                "BLK": 3,
                "TO": 4,
                "PF": 3,
                "PTS": 33,
                "PLUS_MINUS": 12,
                "USG_PCT": 0.35,
                "IS_STARTER": 1,
                "MATCHUP": "vs BOS",
            },
            "1630567": {  # Damian Lillard
                "PLAYER_ID": 1630567,
                "PLAYER_NAME": "Damian Lillard",
                "TEAM_ID": 1610612749,
                "MIN": "33:12",
                "FGM": 9,
                "FGA": 18,
                "FG_PCT": 0.500,
                "FG3M": 5,
                "FG3A": 12,
                "FG3_PCT": 0.417,
                "FTM": 6,
                "FTA": 6,
                "FT_PCT": 1.000,
                "OREB": 0,
                "DREB": 4,
                "REB": 4,
                "AST": 8,
                "STL": 1,
                "BLK": 0,
                "TO": 2,
                "PF": 2,
                "PTS": 29,
                "PLUS_MINUS": 10,
                "USG_PCT": 0.28,
                "IS_STARTER": 1,
                "MATCHUP": "vs BOS",
            },
        },
    }


@pytest.fixture
def sample_player_games() -> Dict:
    """Sample player games data for testing."""
    return {
        "player_id": 203507,
        "player_name": "Giannis Antetokounmpo",
        "season": "2024-25",
        "last_updated": "2024-11-01T12:00:00",
        "games": [
            {
                "date": "2024-10-25",
                "game_id": "0022300001",
                "TEAM_ID": 1610612749,
                "MIN": "34:00",
                "FGM": 10,
                "FGA": 18,
                "FG_PCT": 0.556,
                "FG3M": 0,
                "FG3A": 2,
                "FTM": 6,
                "FTA": 8,
                "REB": 12,
                "AST": 6,
                "STL": 1,
                "BLK": 2,
                "TO": 3,
                "PTS": 26,
                "IS_STARTER": 1,
                "MATCHUP": "@ PHI",
            },
            {
                "date": "2024-10-27",
                "game_id": "0022300002",
                "TEAM_ID": 1610612749,
                "MIN": "36:30",
                "FGM": 14,
                "FGA": 22,
                "FG_PCT": 0.636,
                "FG3M": 2,
                "FG3A": 4,
                "FTM": 10,
                "FTA": 12,
                "REB": 14,
                "AST": 8,
                "STL": 2,
                "BLK": 3,
                "TO": 4,
                "PTS": 40,
                "IS_STARTER": 1,
                "MATCHUP": "vs CHI",
            },
            {
                "date": "2024-10-29",
                "game_id": "0022300003",
                "TEAM_ID": 1610612749,
                "MIN": "32:00",
                "FGM": 8,
                "FGA": 16,
                "FG_PCT": 0.500,
                "FG3M": 1,
                "FG3A": 3,
                "FTM": 5,
                "FTA": 6,
                "REB": 10,
                "AST": 5,
                "STL": 1,
                "BLK": 1,
                "TO": 2,
                "PTS": 22,
                "IS_STARTER": 1,
                "MATCHUP": "@ BKN",
            },
        ],
    }


@pytest.fixture
def sample_season_stats() -> Dict:
    """Sample season stats for testing."""
    return {
        "games_played": 10,
        "fgm": 11.2,
        "fga": 19.5,
        "fg_pct": 0.574,
        "ftm": 7.3,
        "fta": 9.8,
        "ft_pct": 0.745,
        "threes": 1.4,
        "points": 31.1,
        "rebounds": 11.8,
        "assists": 6.5,
        "steals": 1.3,
        "blocks": 2.1,
        "turnovers": 3.2,
    }


@pytest.fixture
def sample_roster() -> Dict[str, list]:
    """Sample roster data for testing."""
    return {
        "2024-11-01": [
            {
                "player_key": "nba.p.3704",
                "name": {"full": "Giannis Antetokounmpo"},
                "selected_position": {"position": "PF"},
            },
            {
                "player_key": "nba.p.5432",
                "name": {"full": "Damian Lillard"},
                "selected_position": {"position": "PG"},
            },
            {
                "player_key": "nba.p.6789",
                "name": {"full": "Injured Player"},
                "selected_position": {"position": "IL"},
            },
            {
                "player_key": "nba.p.9876",
                "name": {"full": "Bench Player"},
                "selected_position": {"position": "BN"},
            },
        ]
    }


@pytest.fixture
def sample_stat_categories() -> list:
    """Sample stat categories for testing."""
    return [
        {
            "stat_id": "0",
            "display_name": "FG%",
            "sort_order": "1",
            "is_only_display_stat": 0,
        },
        {
            "stat_id": "1",
            "display_name": "FT%",
            "sort_order": "1",
            "is_only_display_stat": 0,
        },
        {
            "stat_id": "2",
            "display_name": "3PTM",
            "sort_order": "1",
            "is_only_display_stat": 0,
        },
        {
            "stat_id": "3",
            "display_name": "PTS",
            "sort_order": "1",
            "is_only_display_stat": 0,
        },
        {
            "stat_id": "4",
            "display_name": "REB",
            "sort_order": "1",
            "is_only_display_stat": 0,
        },
        {
            "stat_id": "5",
            "display_name": "AST",
            "sort_order": "1",
            "is_only_display_stat": 0,
        },
        {
            "stat_id": "6",
            "display_name": "STL",
            "sort_order": "1",
            "is_only_display_stat": 0,
        },
        {
            "stat_id": "7",
            "display_name": "BLK",
            "sort_order": "1",
            "is_only_display_stat": 0,
        },
        {
            "stat_id": "8",
            "display_name": "TO",
            "sort_order": "0",
            "is_only_display_stat": 0,
        },  # Ascending (lower is better)
    ]


@pytest.fixture
def mock_week_dates():
    """Returns consistent week dates for testing: (week_start, week_end, today)."""
    return ("2024-11-04", "2024-11-10", "2024-11-06")  # Wed is today


@pytest.fixture
def mock_roster_with_positions():
    """Returns a function to create roster data with player positions by date."""

    def _create_roster(players_by_date: Dict[str, list]) -> Dict[str, list]:
        """
        Create roster data structure.

        Args:
            players_by_date: Dict mapping date string to list of (player_key, name, position) tuples

        Returns:
            Dict mapping date to list of player dicts
        """
        roster = {}
        for date_str, players in players_by_date.items():
            roster[date_str] = []
            for player_key, name, position in players:
                roster[date_str].append(
                    {
                        "player_key": player_key,
                        "name": {"full": name},
                        "selected_position": {"position": position},
                    }
                )
        return roster

    return _create_roster


@pytest.fixture
def mock_schedule_by_player():
    """Returns a function to create schedule data for players."""

    def _create_schedule(schedules: Dict[int, list]) -> Dict[int, list]:
        """
        Create schedule data structure.

        Args:
            schedules: Dict mapping NBA player ID to list of game date strings

        Returns:
            Dict mapping player ID to game dates
        """
        return schedules

    return _create_schedule


@pytest.fixture
def mock_boxscore_by_player_date():
    """Returns a function to create boxscore data."""

    def _create_boxscore(boxscores: Dict[tuple, Dict]):
        """
        Create boxscore data structure.

        Args:
            boxscores: Dict mapping (player_nba_id, date_str) to stats dict

        Returns:
            Dict for boxscore lookups
        """
        return boxscores

    return _create_boxscore


@pytest.fixture
def mock_player_season_stats():
    """Returns a function to create season stats for players."""

    def _create_stats(stats: Dict[int, Dict]):
        """
        Create season stats structure.

        Args:
            stats: Dict mapping NBA player ID to season stats dict

        Returns:
            Dict for season stats lookups
        """
        return stats

    return _create_stats


@pytest.fixture
def mock_boxscore_cache_setup(tmp_path):
    """Set up mock boxscore cache with metadata and season stats directory."""
    from pathlib import Path
    from unittest.mock import MagicMock, Mock

    # Create temporary cache directory structure
    cache_dir = tmp_path / ".shams"
    cache_dir.mkdir()
    season_stats_dir = cache_dir / "season_stats" / "2024-25"
    season_stats_dir.mkdir(parents=True)

    # Create a dummy stats file so the directory check passes
    (season_stats_dir / "dummy.json").write_text("{}")

    metadata = {"games_cached": 100, "season": "2024-25", "last_updated": "2024-11-06"}

    return {"cache_dir": cache_dir, "metadata": metadata, "season": "2024-25"}


@pytest.fixture
def mock_matchup_context():
    """Create a mock matchup context object."""
    from unittest.mock import Mock

    matchup = Mock()
    matchup.week_start = "2024-11-04"
    matchup.week_end = "2024-11-10"
    matchup.week = "3"

    # Mock teams structure
    matchup.teams = [
        {"team": {"team_key": "nba.l.12345.t.1", "name": "Test Team"}},
        {"team": {"team_key": "nba.l.12345.t.2", "name": "Opponent Team"}},
    ]

    return matchup
