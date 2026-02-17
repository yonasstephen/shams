"""Tests for game type settings and filtering logic."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from tools.schedule.game_type_settings import (
    DEFAULT_SETTINGS,
    get_game_type,
    is_fantasy_eligible_game,
    load_settings,
    save_settings,
)


class TestGetGameType:
    """Tests for get_game_type function that classifies games."""

    @pytest.mark.unit
    def test_regular_season_game(self):
        """Regular season games have empty gameLabel and gameSubtype."""
        row = {"gameLabel": "", "gameSubtype": "", "gameSubLabel": ""}
        assert get_game_type(row) == "regular_season"

    @pytest.mark.unit
    def test_regular_season_game_with_none_values(self):
        """Regular season games might have None values."""
        row = {"gameLabel": None, "gameSubtype": None, "gameSubLabel": None}
        assert get_game_type(row) == "regular_season"

    @pytest.mark.unit
    def test_nba_cup_group_stage(self):
        """NBA Cup group stage has gameSubtype='in-season'."""
        row = {
            "gameLabel": "Emirates NBA Cup",
            "gameSubtype": "in-season",
            "gameSubLabel": "East Group A",
        }
        assert get_game_type(row) == "nba_cup_group_stage"

    @pytest.mark.unit
    def test_nba_cup_knockout_quarterfinal(self):
        """NBA Cup quarterfinal is knockout but not championship."""
        row = {
            "gameLabel": "Emirates NBA Cup",
            "gameSubtype": "in-season-knockout",
            "gameSubLabel": "East Quarterfinal",
        }
        assert get_game_type(row) == "nba_cup_knockout"

    @pytest.mark.unit
    def test_nba_cup_knockout_semifinal(self):
        """NBA Cup semifinal is knockout but not championship."""
        row = {
            "gameLabel": "Emirates NBA Cup",
            "gameSubtype": "in-season-knockout",
            "gameSubLabel": "West Semifinal",
        }
        assert get_game_type(row) == "nba_cup_knockout"

    @pytest.mark.unit
    def test_nba_cup_final_championship(self):
        """NBA Cup final/championship game."""
        row = {
            "gameLabel": "Emirates NBA Cup",
            "gameSubtype": "in-season-knockout",
            "gameSubLabel": "Championship",
        }
        assert get_game_type(row) == "nba_cup_final"

    @pytest.mark.unit
    def test_preseason_game(self):
        """Preseason games have gameLabel='Preseason'."""
        row = {"gameLabel": "Preseason", "gameSubtype": "", "gameSubLabel": ""}
        assert get_game_type(row) == "preseason"

    @pytest.mark.unit
    def test_all_star_game(self):
        """All-Star game."""
        row = {"gameLabel": "All-Star", "gameSubtype": "", "gameSubLabel": ""}
        assert get_game_type(row) == "all_star"

    @pytest.mark.unit
    def test_all_star_championship(self):
        """All-Star Championship game."""
        row = {
            "gameLabel": "All-Star Championship",
            "gameSubtype": "",
            "gameSubLabel": "",
        }
        assert get_game_type(row) == "all_star"

    @pytest.mark.unit
    def test_play_in_tournament(self):
        """Play-In Tournament game."""
        row = {
            "gameLabel": "SoFi Play-In Tournament",
            "gameSubtype": "",
            "gameSubLabel": "",
        }
        assert get_game_type(row) == "play_in"

    @pytest.mark.unit
    def test_playoffs_first_round(self):
        """Playoffs first round game."""
        row = {"gameLabel": "East First Round", "gameSubtype": "", "gameSubLabel": "Game 1"}
        assert get_game_type(row) == "playoffs_first_round"

    @pytest.mark.unit
    def test_playoffs_conf_semifinals(self):
        """Playoffs conference semifinals game."""
        row = {
            "gameLabel": "West Conf. Semifinals",
            "gameSubtype": "",
            "gameSubLabel": "Game 3",
        }
        assert get_game_type(row) == "playoffs_conf_semis"

    @pytest.mark.unit
    def test_playoffs_conf_finals(self):
        """Playoffs conference finals game."""
        row = {
            "gameLabel": "East Conf. Finals",
            "gameSubtype": "",
            "gameSubLabel": "Game 5",
        }
        assert get_game_type(row) == "playoffs_conf_finals"

    @pytest.mark.unit
    def test_nba_finals(self):
        """NBA Finals game."""
        row = {"gameLabel": "NBA Finals", "gameSubtype": "", "gameSubLabel": "Game 1"}
        assert get_game_type(row) == "nba_finals"

    @pytest.mark.unit
    def test_global_games(self):
        """Global/international games."""
        row = {
            "gameLabel": "NBA Mexico City Game",
            "gameSubtype": "Global Games",
            "gameSubLabel": "",
        }
        assert get_game_type(row) == "global_games"


class TestIsFantasyEligibleGame:
    """Tests for is_fantasy_eligible_game function."""

    @pytest.mark.unit
    def test_regular_season_enabled_by_default(self):
        """Regular season games should be enabled by default."""
        row = {"gameLabel": "", "gameSubtype": "", "gameSubLabel": ""}
        assert is_fantasy_eligible_game(row, DEFAULT_SETTINGS) is True

    @pytest.mark.unit
    def test_nba_cup_group_stage_enabled_by_default(self):
        """NBA Cup group stage should be enabled by default."""
        row = {
            "gameLabel": "Emirates NBA Cup",
            "gameSubtype": "in-season",
            "gameSubLabel": "East Group A",
        }
        assert is_fantasy_eligible_game(row, DEFAULT_SETTINGS) is True

    @pytest.mark.unit
    def test_nba_cup_knockout_enabled_by_default(self):
        """NBA Cup knockout (non-final) should be enabled by default."""
        row = {
            "gameLabel": "Emirates NBA Cup",
            "gameSubtype": "in-season-knockout",
            "gameSubLabel": "East Quarterfinal",
        }
        assert is_fantasy_eligible_game(row, DEFAULT_SETTINGS) is True

    @pytest.mark.unit
    def test_nba_cup_final_disabled_by_default(self):
        """NBA Cup final should be disabled by default."""
        row = {
            "gameLabel": "Emirates NBA Cup",
            "gameSubtype": "in-season-knockout",
            "gameSubLabel": "Championship",
        }
        assert is_fantasy_eligible_game(row, DEFAULT_SETTINGS) is False

    @pytest.mark.unit
    def test_preseason_disabled_by_default(self):
        """Preseason games should be disabled by default."""
        row = {"gameLabel": "Preseason", "gameSubtype": "", "gameSubLabel": ""}
        assert is_fantasy_eligible_game(row, DEFAULT_SETTINGS) is False

    @pytest.mark.unit
    def test_all_star_disabled_by_default(self):
        """All-Star games should be disabled by default."""
        row = {"gameLabel": "All-Star", "gameSubtype": "", "gameSubLabel": ""}
        assert is_fantasy_eligible_game(row, DEFAULT_SETTINGS) is False

    @pytest.mark.unit
    def test_playoffs_disabled_by_default(self):
        """Playoff games should be disabled by default."""
        row = {"gameLabel": "NBA Finals", "gameSubtype": "", "gameSubLabel": "Game 1"}
        assert is_fantasy_eligible_game(row, DEFAULT_SETTINGS) is False

    @pytest.mark.unit
    def test_custom_settings_enable_nba_cup_final(self):
        """Custom settings can enable NBA Cup final."""
        row = {
            "gameLabel": "Emirates NBA Cup",
            "gameSubtype": "in-season-knockout",
            "gameSubLabel": "Championship",
        }
        custom_settings = {**DEFAULT_SETTINGS, "nba_cup_final": True}
        assert is_fantasy_eligible_game(row, custom_settings) is True

    @pytest.mark.unit
    def test_custom_settings_disable_regular_season(self):
        """Custom settings can disable regular season (edge case)."""
        row = {"gameLabel": "", "gameSubtype": "", "gameSubLabel": ""}
        custom_settings = {**DEFAULT_SETTINGS, "regular_season": False}
        assert is_fantasy_eligible_game(row, custom_settings) is False

    @pytest.mark.unit
    def test_custom_settings_enable_playoffs(self):
        """Custom settings can enable playoff games."""
        row = {"gameLabel": "NBA Finals", "gameSubtype": "", "gameSubLabel": "Game 7"}
        custom_settings = {**DEFAULT_SETTINGS, "nba_finals": True}
        assert is_fantasy_eligible_game(row, custom_settings) is True


class TestSettingsPersistence:
    """Tests for saving and loading settings."""

    @pytest.mark.unit
    def test_save_and_load_settings(self):
        """Settings can be saved and loaded correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_file = Path(tmpdir) / "game_type_settings.json"

            # Mock the settings file path
            with patch(
                "tools.schedule.game_type_settings.get_settings_file_path",
                return_value=settings_file,
            ):
                # Save custom settings
                custom_settings = {
                    "regular_season": True,
                    "nba_cup_final": True,  # Changed from default
                    "preseason": True,  # Changed from default
                }
                save_settings(custom_settings)

                # Load and verify
                loaded = load_settings()
                assert loaded["nba_cup_final"] is True
                assert loaded["preseason"] is True
                assert loaded["regular_season"] is True

    @pytest.mark.unit
    def test_load_settings_returns_defaults_when_file_missing(self):
        """Load returns defaults when settings file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_file = Path(tmpdir) / "nonexistent.json"

            with patch(
                "tools.schedule.game_type_settings.get_settings_file_path",
                return_value=settings_file,
            ):
                loaded = load_settings()
                assert loaded == DEFAULT_SETTINGS

    @pytest.mark.unit
    def test_load_settings_merges_with_defaults(self):
        """Load merges saved settings with defaults for new keys."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_file = Path(tmpdir) / "game_type_settings.json"

            # Create a file with only some settings (simulating old config)
            partial_settings = {"regular_season": True, "preseason": True}
            with open(settings_file, "w", encoding="utf-8") as f:
                json.dump(partial_settings, f)

            with patch(
                "tools.schedule.game_type_settings.get_settings_file_path",
                return_value=settings_file,
            ):
                loaded = load_settings()
                # Should have the saved values
                assert loaded["preseason"] is True
                # Should have defaults for missing keys
                assert loaded["nba_cup_final"] is False
                assert loaded["nba_finals"] is False


class TestScheduleFilteringIntegration:
    """Integration tests for schedule filtering with game type settings."""

    @pytest.mark.unit
    def test_filter_excludes_nba_cup_final_from_schedule(self):
        """NBA Cup final game should be filtered out with default settings."""
        # Simulate schedule rows
        games = [
            # Regular season game - should be included
            {
                "gameId": "0022500001",
                "gameDateEst": "2025-12-15T00:00:00Z",
                "homeTeam_teamId": 1610612752,
                "awayTeam_teamId": 1610612759,
                "gameLabel": "",
                "gameSubtype": "",
                "gameSubLabel": "",
            },
            # NBA Cup Final - should be excluded
            {
                "gameId": "0062500001",
                "gameDateEst": "2025-12-16T00:00:00Z",
                "homeTeam_teamId": 1610612752,
                "awayTeam_teamId": 1610612759,
                "gameLabel": "Emirates NBA Cup",
                "gameSubtype": "in-season-knockout",
                "gameSubLabel": "Championship",
            },
            # Regular season game - should be included
            {
                "gameId": "0022500002",
                "gameDateEst": "2025-12-17T00:00:00Z",
                "homeTeam_teamId": 1610612752,
                "awayTeam_teamId": 1610612751,
                "gameLabel": "",
                "gameSubtype": "",
                "gameSubLabel": "",
            },
        ]

        # Filter using default settings
        eligible_games = [
            g for g in games if is_fantasy_eligible_game(g, DEFAULT_SETTINGS)
        ]

        # Should have 2 games (excluding the NBA Cup Final)
        assert len(eligible_games) == 2
        assert all(g["gameId"] != "0062500001" for g in eligible_games)
        assert any(g["gameId"] == "0022500001" for g in eligible_games)
        assert any(g["gameId"] == "0022500002" for g in eligible_games)

    @pytest.mark.unit
    def test_filter_includes_nba_cup_knockout_non_final(self):
        """NBA Cup knockout games (non-final) should be included by default."""
        games = [
            # NBA Cup Quarterfinal - should be included
            {
                "gameId": "0062400001",
                "gameDateEst": "2025-12-09T00:00:00Z",
                "homeTeam_teamId": 1610612752,
                "awayTeam_teamId": 1610612759,
                "gameLabel": "Emirates NBA Cup",
                "gameSubtype": "in-season-knockout",
                "gameSubLabel": "East Quarterfinal",
            },
            # NBA Cup Semifinal - should be included
            {
                "gameId": "0062400002",
                "gameDateEst": "2025-12-13T00:00:00Z",
                "homeTeam_teamId": 1610612752,
                "awayTeam_teamId": 1610612753,
                "gameLabel": "Emirates NBA Cup",
                "gameSubtype": "in-season-knockout",
                "gameSubLabel": "East Semifinal",
            },
            # NBA Cup Final - should be excluded
            {
                "gameId": "0062500001",
                "gameDateEst": "2025-12-16T00:00:00Z",
                "homeTeam_teamId": 1610612752,
                "awayTeam_teamId": 1610612759,
                "gameLabel": "Emirates NBA Cup",
                "gameSubtype": "in-season-knockout",
                "gameSubLabel": "Championship",
            },
        ]

        eligible_games = [
            g for g in games if is_fantasy_eligible_game(g, DEFAULT_SETTINGS)
        ]

        # Should have 2 games (quarterfinal and semifinal, excluding final)
        assert len(eligible_games) == 2
        assert any(g["gameSubLabel"] == "East Quarterfinal" for g in eligible_games)
        assert any(g["gameSubLabel"] == "East Semifinal" for g in eligible_games)
        assert all(g["gameSubLabel"] != "Championship" for g in eligible_games)

    @pytest.mark.unit
    def test_filter_excludes_preseason_and_allstar(self):
        """Preseason and All-Star games should be excluded by default."""
        games = [
            # Preseason game
            {
                "gameId": "0012500001",
                "gameDateEst": "2025-10-05T00:00:00Z",
                "gameLabel": "Preseason",
                "gameSubtype": "",
                "gameSubLabel": "",
            },
            # All-Star game
            {
                "gameId": "0012500002",
                "gameDateEst": "2026-02-16T00:00:00Z",
                "gameLabel": "All-Star",
                "gameSubtype": "",
                "gameSubLabel": "",
            },
            # Regular season
            {
                "gameId": "0022500001",
                "gameDateEst": "2025-11-01T00:00:00Z",
                "gameLabel": "",
                "gameSubtype": "",
                "gameSubLabel": "",
            },
        ]

        eligible_games = [
            g for g in games if is_fantasy_eligible_game(g, DEFAULT_SETTINGS)
        ]

        # Should only have the regular season game
        assert len(eligible_games) == 1
        assert eligible_games[0]["gameId"] == "0022500001"

    @pytest.mark.unit
    def test_filter_with_custom_settings_includes_all(self):
        """With all settings enabled, all games should be included."""
        games = [
            {"gameId": "1", "gameLabel": "", "gameSubtype": "", "gameSubLabel": ""},
            {
                "gameId": "2",
                "gameLabel": "Emirates NBA Cup",
                "gameSubtype": "in-season-knockout",
                "gameSubLabel": "Championship",
            },
            {"gameId": "3", "gameLabel": "Preseason", "gameSubtype": "", "gameSubLabel": ""},
            {"gameId": "4", "gameLabel": "NBA Finals", "gameSubtype": "", "gameSubLabel": "Game 1"},
        ]

        # Enable all settings
        all_enabled = {key: True for key in DEFAULT_SETTINGS}

        eligible_games = [g for g in games if is_fantasy_eligible_game(g, all_enabled)]

        # All games should be included
        assert len(eligible_games) == 4

