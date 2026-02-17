"""Tests for matchup projection logic."""

from __future__ import annotations

from datetime import date
from unittest.mock import Mock, patch

import pytest

from tools.matchup import matchup_projection
from tools.schedule.schedule_fetcher import PlayerSchedule


@pytest.mark.unit
def test_player_is_active_regular_position():
    """Test that player with regular position is active."""
    player = {"name": {"full": "Test Player"}, "selected_position": {"position": "PG"}}

    assert matchup_projection._player_is_active(player) is True


@pytest.mark.unit
def test_player_is_active_bench():
    """Test that benched player is inactive."""
    player = {"name": {"full": "Test Player"}, "selected_position": {"position": "BN"}}

    assert matchup_projection._player_is_active(player) is False


@pytest.mark.unit
def test_player_is_active_injured_list():
    """Test that player on IL is inactive."""
    player = {"name": {"full": "Test Player"}, "selected_position": {"position": "IL"}}

    assert matchup_projection._player_is_active(player) is False


@pytest.mark.unit
def test_player_is_active_injured_list_plus():
    """Test that player on IL+ is inactive."""
    player = {"name": {"full": "Test Player"}, "selected_position": {"position": "IL+"}}

    assert matchup_projection._player_is_active(player) is False


@pytest.mark.unit
def test_player_is_active_no_position():
    """Test that player with no position is inactive."""
    player = {"name": {"full": "Test Player"}, "selected_position": {"position": ""}}

    assert matchup_projection._player_is_active(player) is False

    player_no_pos = {"name": {"full": "Test Player"}}

    assert matchup_projection._player_is_active(player_no_pos) is False


@pytest.mark.unit
def test_build_player_active_dates(sample_roster):
    """Test building map of player active dates."""
    active_dates = matchup_projection._build_player_active_dates(sample_roster)

    # Active players should have their dates recorded
    assert "nba.p.3704" in active_dates  # Giannis (PF)
    assert "nba.p.5432" in active_dates  # Lillard (PG)
    assert "2024-11-01" in active_dates["nba.p.3704"]

    # Inactive players should not be in active dates
    assert "nba.p.6789" not in active_dates  # IL player
    assert "nba.p.9876" not in active_dates  # Bench player


@pytest.mark.unit
def test_calculate_projected_points(sample_stat_categories):
    """Test calculating projected team points."""
    team_a_projection = {
        "0": 0.45,  # FG%
        "1": 0.80,  # FT%
        "2": 12.0,  # 3PTM
        "3": 110.0,  # PTS
        "4": 45.0,  # REB
        "5": 28.0,  # AST
        "6": 8.0,  # STL
        "7": 5.0,  # BLK
        "8": 12.0,  # TO (lower is better)
    }

    team_b_projection = {
        "0": 0.42,  # FG%
        "1": 0.75,  # FT%
        "2": 10.0,  # 3PTM
        "3": 105.0,  # PTS
        "4": 42.0,  # REB
        "5": 30.0,  # AST
        "6": 7.0,  # STL
        "7": 6.0,  # BLK
        "8": 15.0,  # TO (lower is better)
    }

    points_a, points_b = matchup_projection._calculate_projected_points(
        sample_stat_categories, team_a_projection, team_b_projection
    )

    # Team A should win: FG%, FT%, 3PTM, PTS, REB, STL, TO = 7 categories
    # Team B should win: AST, BLK = 2 categories
    assert points_a["win"] == 7.0
    assert points_a["loss"] == 2.0
    assert points_b["win"] == 2.0
    assert points_b["loss"] == 7.0


@pytest.mark.unit
def test_calculate_projected_points_tie():
    """Test calculating projected points with a tie."""
    sample_categories = [
        {
            "stat_id": "0",
            "display_name": "PTS",
            "sort_order": "1",
            "is_only_display_stat": 0,
        },
        {
            "stat_id": "1",
            "display_name": "REB",
            "sort_order": "1",
            "is_only_display_stat": 0,
        },
    ]

    team_a_projection = {"0": 100.0, "1": 40.0}
    team_b_projection = {"0": 100.0, "1": 45.0}  # Tie in PTS

    points_a, points_b = matchup_projection._calculate_projected_points(
        sample_categories, team_a_projection, team_b_projection
    )

    # PTS is tie (1.0 tie each), REB goes to B
    # Ties count as 1.0 tie, not 0.5 points
    assert points_a["tie"] == 1.0
    assert points_a["win"] == 0.0
    assert points_a["loss"] == 1.0
    assert points_b["tie"] == 1.0
    assert points_b["win"] == 1.0
    assert points_b["loss"] == 0.0
    # Total = wins only (ties don't add to total)
    assert points_a["total"] == 0.0
    assert points_b["total"] == 1.0


@pytest.mark.unit
@patch("tools.player.player_fetcher.player_id_lookup")
@patch("tools.boxscore.boxscore_cache.load_player_season_stats")
def test_project_player_stats(mock_load_stats, mock_lookup, sample_stat_categories):
    """Test projecting player stats for game dates."""
    mock_lookup.return_value = 203507  # Giannis
    mock_load_stats.return_value = {
        "fg_pct": 0.574,
        "ft_pct": 0.745,
        "threes": 1.4,
        "points": 31.1,
        "rebounds": 11.8,
        "assists": 6.5,
        "steals": 1.3,
        "blocks": 2.1,
        "turnovers": 3.2,
    }

    player = {"player_key": "nba.p.3704", "name": {"full": "Giannis Antetokounmpo"}}

    game_dates = ["2024-11-01", "2024-11-03", "2024-11-05"]  # 3 games

    projected = matchup_projection._project_player_stats(
        "league_key", player, game_dates, sample_stat_categories, "2024-25"
    )

    # Percentages should not be multiplied
    assert projected["0"] == 0.574  # FG%
    assert projected["1"] == 0.745  # FT%

    # Counting stats should be multiplied by games
    assert projected["2"] == 1.4 * 3  # 3PTM
    assert projected["3"] == 31.1 * 3  # PTS
    assert projected["4"] == 11.8 * 3  # REB
    assert projected["5"] == 6.5 * 3  # AST
    assert projected["6"] == 1.3 * 3  # STL
    assert projected["7"] == 2.1 * 3  # BLK
    assert projected["8"] == 3.2 * 3  # TO


@pytest.mark.unit
@patch("tools.player.player_fetcher.player_id_lookup")
def test_project_player_stats_no_nba_id(mock_lookup, sample_stat_categories):
    """Test projecting stats when NBA ID not found."""
    mock_lookup.return_value = None

    player = {"player_key": "nba.p.unknown", "name": {"full": "Unknown Player"}}

    game_dates = ["2024-11-01"]

    projected = matchup_projection._project_player_stats(
        "league_key", player, game_dates, sample_stat_categories, "2024-25"
    )

    # Should return zeros for all stats
    for stat_id in ["0", "1", "2", "3", "4", "5", "6", "7", "8"]:
        assert projected[stat_id] == 0.0


@pytest.mark.unit
def test_date_range():
    """Test _date_range helper function."""
    start = date(2024, 11, 1)
    end = date(2024, 11, 3)

    dates = list(matchup_projection._date_range(start, end))

    assert len(dates) == 3
    assert dates[0] == date(2024, 11, 1)
    assert dates[1] == date(2024, 11, 2)
    assert dates[2] == date(2024, 11, 3)


@pytest.mark.unit
def test_stat_sort_order():
    """Test _stat_sort_order helper function."""
    stat_asc = {"sort_order": "0"}
    stat_desc = {"sort_order": "1"}
    stat_invalid = {"sort_order": "invalid"}

    assert matchup_projection._stat_sort_order(stat_asc) == 0
    assert matchup_projection._stat_sort_order(stat_desc) == 1
    assert matchup_projection._stat_sort_order(stat_invalid) == 0


@pytest.mark.unit
def test_is_category_desc():
    """Test _is_category_desc helper function."""
    stat_asc_str = {"sort_order": "0"}
    stat_asc_int = {"sort_order": 0}
    stat_asc_word = {"sort_order": "asc"}
    stat_desc = {"sort_order": "1"}

    assert matchup_projection._is_category_desc(stat_asc_str) is True
    assert matchup_projection._is_category_desc(stat_asc_int) is True
    assert matchup_projection._is_category_desc(stat_asc_word) is True
    assert matchup_projection._is_category_desc(stat_desc) is False


@pytest.mark.unit
def test_player_key():
    """Test _player_key helper function."""
    player_with_key = {"player_key": "nba.p.3704"}
    player_without_key = {"name": "Test"}

    assert matchup_projection._player_key(player_with_key) == "nba.p.3704"
    assert matchup_projection._player_key(player_without_key) is None


@pytest.mark.unit
def test_serialize_team_entry():
    """Test _serialize_team_entry helper function."""
    # Dict format
    team_dict = {"team_key": "nba.l.12345.t.1", "name": "Team A"}
    result = matchup_projection._serialize_team_entry(team_dict)
    assert result == team_dict

    # Nested format
    nested = {"team": {"team_key": "nba.l.12345.t.1", "name": "Team A"}}
    result = matchup_projection._serialize_team_entry(nested)
    assert result["team_key"] == "nba.l.12345.t.1"


@pytest.mark.unit
def test_ensure_team_key():
    """Test _ensure_team_key helper function."""
    # String
    assert matchup_projection._ensure_team_key("nba.l.12345.t.1") == "nba.l.12345.t.1"

    # Bytes
    assert matchup_projection._ensure_team_key(b"nba.l.12345.t.1") == "nba.l.12345.t.1"

    # None
    assert matchup_projection._ensure_team_key(None) is None

    # Other type
    assert matchup_projection._ensure_team_key(12345) is None


# ============================================================================
# Integration Tests for Roster Contributions vs Remaining Projections
# ============================================================================
# These tests validate the critical separation between current contributions
# (actual stats accumulated) and remaining projections (future expected stats).
#
# To run these tests:
#   cd tools/tests && pipenv run pytest test_matchup_projection.py::TestRosterContributionsVsProjections -v
#
# To run with coverage:
#   cd tools/tests && pipenv run pytest test_matchup_projection.py --cov=tools.matchup.matchup_projection
# ============================================================================


def create_mock_roster_entry(player_key: str, name: str, position: str) -> dict:
    """Create a single roster entry."""
    return {
        "player_key": player_key,
        "name": {"full": name},
        "selected_position": {"position": position},
    }


def create_mock_schedule(player_nba_id: int, game_dates: list) -> dict:
    """Build schedule response for a player."""
    return {player_nba_id: game_dates}


def create_mock_boxscore(player_nba_id: int, date_str: str, stats: dict) -> tuple:
    """
    Build boxscore response key-value pair.

    Args:
        player_nba_id: NBA player ID
        date_str: Date string
        stats: Dict with stat values (points, rebounds, assists, etc.)

    Returns:
        Tuple of ((player_id, date), stats_dict)
    """
    return ((player_nba_id, date_str), stats)


def create_mock_season_stats(
    points: float = 20.0,
    rebounds: float = 8.0,
    assists: float = 5.0,
    steals: float = 1.0,
    blocks: float = 1.0,
    turnovers: float = 2.0,
    threes: float = 2.0,
    fg_pct: float = 0.45,
    ft_pct: float = 0.80,
) -> dict:
    """Create season stats dict with defaults."""
    return {
        "games_played": 10,
        "points": points,
        "rebounds": rebounds,
        "assists": assists,
        "steals": steals,
        "blocks": blocks,
        "turnovers": turnovers,
        "threes": threes,
        "fg_pct": fg_pct,
        "ft_pct": ft_pct,
        "fgm": points / 2.2,  # Approximate
        "fga": points / 2.2 / fg_pct if fg_pct > 0 else 0,
        "ftm": points * 0.2,
        "fta": points * 0.2 / ft_pct if ft_pct > 0 else 0,
    }


def assert_contribution_separation(
    result: dict,
    player_key: str,
    expected_current_games: int,
    expected_remaining_games: int,
    expected_total_games: int,
    expected_on_roster_today: bool,
    check_current_nonzero: bool = False,
    check_remaining_nonzero: bool = False,
):
    """
    Assert that current and remaining contributions are properly separated.

    Args:
        result: Result from project_matchup()
        player_key: Player to check
        expected_current_games: Expected games_played count
        expected_remaining_games: Expected remaining_games count
        expected_total_games: Expected total_games count
        expected_on_roster_today: Expected is_on_roster_today value
        check_current_nonzero: If True, assert current stats > 0
        check_remaining_nonzero: If True, assert remaining stats > 0
    """
    # Find player in current contributions
    current_contribs = result.get("current_player_contributions", [])
    current_player = None
    for contrib in current_contribs:
        if contrib["player_key"] == player_key:
            current_player = contrib
            break

    # Find player in remaining projections
    remaining_contribs = result.get("player_contributions", [])
    remaining_player = None
    for contrib in remaining_contribs:
        if contrib["player_key"] == player_key:
            remaining_player = contrib
            break

    # Assert games counts
    if current_player:
        assert (
            current_player["games_played"] == expected_current_games
        ), f"Expected {expected_current_games} games_played, got {current_player['games_played']}"
        assert (
            current_player["total_games"] == expected_total_games
        ), f"Expected {expected_total_games} total_games, got {current_player['total_games']}"
        assert (
            current_player["is_on_roster_today"] == expected_on_roster_today
        ), f"Expected is_on_roster_today={expected_on_roster_today}, got {current_player['is_on_roster_today']}"

        if check_current_nonzero:
            # Check that at least one stat is non-zero
            has_stats = any(v > 0 for v in current_player.get("stats", {}).values())
            assert has_stats, f"Expected non-zero current stats for {player_key}"

    if remaining_player:
        assert (
            remaining_player["remaining_games"] == expected_remaining_games
        ), f"Expected {expected_remaining_games} remaining_games, got {remaining_player['remaining_games']}"
        assert (
            remaining_player["total_games"] == expected_total_games
        ), f"Expected {expected_total_games} total_games, got {remaining_player['total_games']}"
        assert (
            remaining_player["is_on_roster_today"] == expected_on_roster_today
        ), f"Expected is_on_roster_today={expected_on_roster_today}, got {remaining_player['is_on_roster_today']}"

        if check_remaining_nonzero:
            # Check that at least one stat is non-zero
            has_stats = any(v > 0 for v in remaining_player.get("stats", {}).values())
            assert has_stats, f"Expected non-zero remaining stats for {player_key}"


# ============================================================================
# Functional Integration Tests - Testing Core Logic with Proper Mocks
# ============================================================================


@pytest.mark.integration
class TestRosterContributionsLogic:
    """
    Simplified integration tests focusing on core contribution logic.
    These tests directly test internal functions with proper mocking.
    """

    @pytest.mark.integration
    def test_aggregate_current_week_contributions_with_boxscore(self):
        """Test that current contributions correctly aggregate boxscore data."""
        from datetime import date

        from tools.matchup import matchup_projection

        # Setup: Create a simple roster with one player active on one date
        roster = {
            "2024-11-05": [
                {
                    "player_key": "nba.p.12345",
                    "name": {"full": "Test Player"},
                    "selected_position": {"position": "PG"},
                }
            ]
        }

        stat_meta = [
            {
                "stat_id": "12",
                "display_name": "PTS",
                "name": "Points",
                "is_only_display_stat": 0,
            },
            {
                "stat_id": "15",
                "display_name": "REB",
                "name": "Rebounds",
                "is_only_display_stat": 0,
            },
        ]

        week_start = date(2024, 11, 4)
        week_end = date(2024, 11, 10)
        today = date(2024, 11, 6)

        # Mock player lookup
        with patch(
            "tools.matchup.matchup_projection.player_fetcher.player_id_lookup",
            return_value=203507,
        ):
            # Mock fetch_player_stats_from_cache to return a game
            with patch(
                "tools.matchup.matchup_projection.player_fetcher.fetch_player_stats_from_cache"
            ) as mock_fetch:
                mock_fetch.return_value = [
                    {
                        "date": "2024-11-05",
                        "PTS": 25.0,
                        "REB": 10.0,
                        "Points": 25.0,
                        "Rebounds": 10.0,
                        "FGM": 10,
                        "FGA": 20,
                        "FTM": 5,
                        "FTA": 6,
                    }
                ]

                # Execute
                (
                    contributions,
                    player_names,
                    player_shooting,
                    is_on_roster,
                    games_played,
                    player_ids,
                ) = matchup_projection._aggregate_current_week_player_contributions(
                    "test_league",
                    roster,
                    week_start,
                    week_end,
                    stat_meta,
                    _season="2024-25",
                )

                # Assert
                assert "nba.p.12345" in contributions
                assert contributions["nba.p.12345"]["12"] == 25.0  # Points
                assert contributions["nba.p.12345"]["15"] == 10.0  # Rebounds
                assert games_played["nba.p.12345"] == 1
                assert player_names["nba.p.12345"] == "Test Player"

    @pytest.mark.integration
    def test_aggregate_projected_contributions_excludes_today_with_boxscore(self):
        """Test that remaining projections exclude today if boxscore exists."""
        from datetime import date

        from tools.matchup import matchup_projection
        from tools.schedule.schedule_fetcher import PlayerSchedule

        # Setup - Player must be on roster for all dates they'll have games
        roster = {
            "2024-11-05": [
                {
                    "player_key": "nba.p.12345",
                    "name": {"full": "Test Player"},
                    "selected_position": {"position": "PG"},
                }
            ],
            "2024-11-06": [
                {
                    "player_key": "nba.p.12345",
                    "name": {"full": "Test Player"},
                    "selected_position": {"position": "PG"},
                }
            ],
            "2024-11-07": [
                {
                    "player_key": "nba.p.12345",
                    "name": {"full": "Test Player"},
                    "selected_position": {"position": "PG"},
                }
            ],
            "2024-11-08": [
                {
                    "player_key": "nba.p.12345",
                    "name": {"full": "Test Player"},
                    "selected_position": {"position": "PG"},
                }
            ],
        }

        stat_meta = [
            {
                "stat_id": "12",
                "display_name": "PTS",
                "name": "Points",
                "is_only_display_stat": 0,
            },
        ]

        week_start = date(2024, 11, 4)
        week_end = date(2024, 11, 10)
        today = date(2024, 11, 6)

        # Mock dependencies
        with patch(
            "tools.matchup.matchup_projection.player_fetcher.player_id_lookup",
            return_value=203507,
        ):
            with patch(
                "tools.matchup.matchup_projection.schedule_fetcher.fetch_player_upcoming_games_from_cache"
            ) as mock_schedule:
                # Player has games on 2024-11-05, 2024-11-06 (today), and 2024-11-08
                mock_schedule.return_value = PlayerSchedule(
                    player_id=203507,
                    game_dates=["2024-11-05", "2024-11-06", "2024-11-08"],
                )

                with patch(
                    "tools.matchup.matchup_projection.boxscore_cache.load_player_games"
                ) as mock_load_games:
                    # Boxscore exists for 2024-11-05 AND 2024-11-06 (today)
                    mock_load_games.return_value = {
                        "player_id": 203507,
                        "player_name": "Test Player",
                        "games": [
                            {"date": "2024-11-05", "PTS": 25.0},
                            {"date": "2024-11-06", "PTS": 20.0},  # Today has boxscore
                        ],
                    }

                    with patch(
                        "tools.matchup.matchup_projection.boxscore_cache.load_player_season_stats"
                    ) as mock_season:
                        mock_season.return_value = {
                            "points": 22.0,
                            "fgm": 9.0,
                            "fga": 20.0,
                            "ftm": 4.0,
                            "fta": 5.0,
                            "fg_pct": 0.45,
                            "ft_pct": 0.80,
                        }

                        # Execute - Mock date.today() to control "today" in the function
                        with patch(
                            "tools.matchup.matchup_projection.date"
                        ) as mock_date_class:
                            mock_date_class.today.return_value = today
                            mock_date_class.side_effect = lambda *args, **kw: date(
                                *args, **kw
                            )
                            (
                                contributions,
                                player_names,
                                total_games,
                                remaining_games,
                                shooting,
                                daily,
                                positions,
                                player_ids,
                            ) = matchup_projection._aggregate_projected_contributions(
                                "test_league",
                                roster,
                                week_start,
                                week_end,
                                stat_meta,
                                season="2024-25",
                            )

                        # Assert: Today (2024-11-06) should be EXCLUDED from remaining since boxscore exists
                        # Only 2024-11-08 should count as remaining
                        assert "nba.p.12345" in remaining_games
                        assert (
                            remaining_games["nba.p.12345"] == 1
                        ), f"Expected 1 remaining game (only 2024-11-08), got {remaining_games['nba.p.12345']}"

                        # Total games should be 3
                        assert total_games["nba.p.12345"] == 3

    @pytest.mark.integration
    def test_aggregate_projected_contributions_includes_today_without_boxscore(self):
        """Test that remaining projections include today if no boxscore exists."""
        from datetime import date

        from tools.matchup import matchup_projection
        from tools.schedule.schedule_fetcher import PlayerSchedule

        # Setup - Player must be on roster for all dates they'll have games
        roster = {
            "2024-11-05": [
                {
                    "player_key": "nba.p.12345",
                    "name": {"full": "Test Player"},
                    "selected_position": {"position": "PG"},
                }
            ],
            "2024-11-06": [
                {
                    "player_key": "nba.p.12345",
                    "name": {"full": "Test Player"},
                    "selected_position": {"position": "PG"},
                }
            ],
            "2024-11-07": [
                {
                    "player_key": "nba.p.12345",
                    "name": {"full": "Test Player"},
                    "selected_position": {"position": "PG"},
                }
            ],
            "2024-11-08": [
                {
                    "player_key": "nba.p.12345",
                    "name": {"full": "Test Player"},
                    "selected_position": {"position": "PG"},
                }
            ],
        }

        stat_meta = [
            {
                "stat_id": "12",
                "display_name": "PTS",
                "name": "Points",
                "is_only_display_stat": 0,
            },
        ]

        week_start = date(2024, 11, 4)
        week_end = date(2024, 11, 10)
        today = date(2024, 11, 6)

        # Mock dependencies
        with patch(
            "tools.matchup.matchup_projection.player_fetcher.player_id_lookup",
            return_value=203507,
        ):
            with patch(
                "tools.matchup.matchup_projection.schedule_fetcher.fetch_player_upcoming_games_from_cache"
            ) as mock_schedule:
                # Player has games on 2024-11-05, 2024-11-06 (today), and 2024-11-08
                mock_schedule.return_value = PlayerSchedule(
                    player_id=203507,
                    game_dates=["2024-11-05", "2024-11-06", "2024-11-08"],
                )

                with patch(
                    "tools.matchup.matchup_projection.boxscore_cache.load_player_games"
                ) as mock_load_games:
                    # Boxscore exists for 2024-11-05 but NOT for 2024-11-06 (today)
                    mock_load_games.return_value = {
                        "player_id": 203507,
                        "player_name": "Test Player",
                        "games": [
                            {"date": "2024-11-05", "PTS": 25.0},
                            # No game for 2024-11-06 - game hasn't been played yet
                        ],
                    }

                    with patch(
                        "tools.matchup.matchup_projection.boxscore_cache.load_player_season_stats"
                    ) as mock_season:
                        mock_season.return_value = {
                            "points": 22.0,
                            "fgm": 9.0,
                            "fga": 20.0,
                            "ftm": 4.0,
                            "fta": 5.0,
                            "fg_pct": 0.45,
                            "ft_pct": 0.80,
                        }

                        # Execute - Mock date.today() to control "today" in the function
                        with patch(
                            "tools.matchup.matchup_projection.date"
                        ) as mock_date_class:
                            mock_date_class.today.return_value = today
                            mock_date_class.side_effect = lambda *args, **kw: date(
                                *args, **kw
                            )
                            (
                                contributions,
                                player_names,
                                total_games,
                                remaining_games,
                                shooting,
                                daily,
                                positions,
                                player_ids,
                            ) = matchup_projection._aggregate_projected_contributions(
                                "test_league",
                                roster,
                                week_start,
                                week_end,
                                stat_meta,
                                season="2024-25",
                            )

                        # Assert: Today (2024-11-06) should be INCLUDED in remaining since no boxscore
                        # Both 2024-11-06 and 2024-11-08 should count
                        assert "nba.p.12345" in remaining_games
                        assert (
                            remaining_games["nba.p.12345"] == 2
                        ), f"Expected 2 remaining games (2024-11-06 and 2024-11-08), got {remaining_games['nba.p.12345']}"

                        # Total games should be 3
                        assert total_games["nba.p.12345"] == 3


@pytest.mark.integration
class TestOptimizedRosterDroppedPlayers:
    """
    Tests for optimized roster handling of dropped players.
    
    Bug fixed: When roster optimization is enabled, dropped players (who were
    on the roster earlier in the week) should NOT be included in optimized
    positions for future dates.
    """

    @pytest.mark.integration
    def test_dropped_player_not_in_optimized_future_dates(self):
        """Test that dropped players are not included in optimization for future dates.
        
        Scenario: Player A was on roster Mon-Wed, then dropped.
        Player B was added Thu onwards.
        When optimizing for Thu/Fri, Player A should NOT be considered.
        """
        from datetime import date
        from typing import Set

        from tools.matchup import matchup_projection
        from tools.schedule.schedule_fetcher import PlayerSchedule

        # Setup: Player A (dropped) was on roster Mon-Wed, Player B added Thu onwards
        roster = {
            # Monday - only Player A on roster
            "2024-11-04": [
                {
                    "player_key": "nba.p.dropped",
                    "name": {"full": "Dropped Player"},
                    "selected_position": {"position": "PG"},
                }
            ],
            # Wednesday - still only Player A
            "2024-11-06": [
                {
                    "player_key": "nba.p.dropped",
                    "name": {"full": "Dropped Player"},
                    "selected_position": {"position": "PG"},
                }
            ],
            # Thursday - Player A dropped, Player B added
            "2024-11-07": [
                {
                    "player_key": "nba.p.new",
                    "name": {"full": "New Player"},
                    "selected_position": {"position": "PG"},
                }
            ],
            # Friday - only Player B
            "2024-11-08": [
                {
                    "player_key": "nba.p.new",
                    "name": {"full": "New Player"},
                    "selected_position": {"position": "PG"},
                }
            ],
        }

        week_start = date(2024, 11, 4)
        week_end = date(2024, 11, 10)

        # Mock league roster positions (import inside function so mock the module)
        with patch(
            "tools.utils.yahoo.fetch_and_cache_league_roster_positions"
        ) as mock_positions:
            mock_positions.return_value = ["PG", "SG", "G", "SF", "PF", "F", "C", "Util", "Util", "BN", "BN"]

            with patch(
                "tools.utils.player_index.get_all_player_ranks"
            ) as mock_ranks:
                mock_ranks.return_value = {}  # No rankings

                with patch(
                    "tools.player.player_fetcher.player_id_lookup"
                ) as mock_lookup:
                    # Map player names to NBA IDs
                    def lookup_side_effect(name):
                        if "Dropped" in name:
                            return 111111
                        elif "New" in name:
                            return 222222
                        return None

                    mock_lookup.side_effect = lookup_side_effect

                    with patch(
                        "tools.schedule.schedule_fetcher.fetch_player_upcoming_games_from_cache"
                    ) as mock_schedule:
                        # Both players have games on Thu and Fri
                        def schedule_side_effect(nba_id, start, end, season):
                            return PlayerSchedule(
                                player_id=nba_id,
                                game_dates=["2024-11-07", "2024-11-08"],  # Thu, Fri
                            )

                        mock_schedule.side_effect = schedule_side_effect

                        with patch(
                            "tools.boxscore.boxscore_cache.load_player_eligibility"
                        ) as mock_eligibility:
                            mock_eligibility.return_value = ["PG", "SG"]

                            # Execute: Build optimized player active dates
                            active_dates, optimized_positions = matchup_projection._build_optimized_player_active_dates(
                                "test_league",
                                roster,
                                week_start,
                                week_end,
                                "2024-25",
                            )

                            # Assert: Dropped player should NOT have active dates for Thu/Fri
                            dropped_active = active_dates.get("nba.p.dropped", set())
                            new_active = active_dates.get("nba.p.new", set())

                            # Dropped player should only be active on Mon and Wed (dates they were on roster)
                            assert "2024-11-04" in dropped_active or dropped_active == set(), \
                                f"Dropped player should be active on Mon if games existed: {dropped_active}"
                            assert "2024-11-07" not in dropped_active, \
                                f"Dropped player should NOT be active on Thu: {dropped_active}"
                            assert "2024-11-08" not in dropped_active, \
                                f"Dropped player should NOT be active on Fri: {dropped_active}"

                            # New player should be active on Thu/Fri (has games on these dates)
                            assert "2024-11-07" in new_active, \
                                f"New player should be active on Thu: {new_active}"
                            assert "2024-11-08" in new_active, \
                                f"New player should be active on Fri: {new_active}"
                            # New player was NOT on roster Mon/Wed, so should not be active there
                            assert "2024-11-04" not in new_active, \
                                f"New player should NOT be active on Mon: {new_active}"
                            assert "2024-11-06" not in new_active, \
                                f"New player should NOT be active on Wed: {new_active}"

                            # Check optimized positions - dropped player should not appear in Thu/Fri
                            thu_positions = optimized_positions.get("2024-11-07", {})
                            fri_positions = optimized_positions.get("2024-11-08", {})

                            assert "nba.p.dropped" not in thu_positions, \
                                f"Dropped player should not have optimized position on Thu: {thu_positions}"
                            assert "nba.p.dropped" not in fri_positions, \
                                f"Dropped player should not have optimized position on Fri: {fri_positions}"

                            # New player should have positions on Thu/Fri
                            assert "nba.p.new" in thu_positions, \
                                f"New player should have optimized position on Thu: {thu_positions}"
                            assert "nba.p.new" in fri_positions, \
                                f"New player should have optimized position on Fri: {fri_positions}"


@pytest.mark.unit
class TestProjectionModes:
    """Tests for different projection modes."""

    def test_projection_mode_season_default(self):
        """Test that season mode is used by default."""
        from unittest.mock import patch

        from tools.matchup import matchup_projection

        # Create mock player and game dates
        player = {
            "player_key": "nba.p.12345",
            "name": {"full": "Test Player"},
        }
        game_dates = ["2024-11-07", "2024-11-08"]

        stat_meta = [
            {"stat_id": "12", "display_name": "PTS", "is_only_display_stat": 0},
        ]

        with patch(
            "tools.matchup.matchup_projection.player_fetcher"
        ) as mock_fetcher, patch(
            "tools.matchup.matchup_projection.boxscore_cache"
        ) as mock_cache:

            mock_fetcher.player_id_lookup.return_value = 203507
            mock_cache.load_player_season_stats.return_value = {
                "points": 25.5,
            }

            result = matchup_projection._project_player_stats(
                "test_league", player, game_dates, stat_meta, "2024-25", "season"
            )

            # Should use season stats: 25.5 * 2 games = 51.0
            assert result["12"] == 51.0
            mock_cache.load_player_season_stats.assert_called_once()

    def test_projection_mode_last3_uses_compute_stats(self):
        """Test that last3 mode uses compute_player_stats."""
        from unittest.mock import patch

        from tools.matchup import matchup_projection
        from tools.player.player_stats import PlayerStats

        player = {
            "player_key": "nba.p.12345",
            "name": {"full": "Test Player"},
        }
        game_dates = ["2024-11-07", "2024-11-08"]

        stat_meta = [
            {"stat_id": "12", "display_name": "PTS", "is_only_display_stat": 0},
        ]

        with patch(
            "tools.matchup.matchup_projection.player_fetcher"
        ) as mock_fetcher, patch(
            "tools.matchup.matchup_projection.compute_player_stats"
        ) as mock_compute:

            mock_fetcher.player_id_lookup.return_value = 203507
            mock_compute.return_value = PlayerStats(
                fg_pct=0.45,
                ft_pct=0.80,
                threes=2.5,
                points=22.0,
                rebounds=8.0,
                assists=5.0,
                steals=1.5,
                blocks=0.5,
                turnovers=2.0,
                games_count=3,
                fgm=8.0,
                fga=18.0,
                ftm=6.0,
                fta=7.5,
                usage_pct=0.28,
                games_started=3,
                plus_minus=5.0,
                minutes=32.5,
            )

            result = matchup_projection._project_player_stats(
                "test_league", player, game_dates, stat_meta, "2024-25", "last3"
            )

            # Should use last3 average: 22.0 * 2 games = 44.0
            assert result["12"] == 44.0
            mock_compute.assert_called_once()
            call_args = mock_compute.call_args
            assert call_args[1]["mode"] == "last3"
