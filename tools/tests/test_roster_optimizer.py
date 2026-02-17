"""Tests for roster optimizer."""

import pytest
from tools.matchup.roster_optimizer import (
    optimize_roster_positions,
    get_active_positions,
    _get_eligible_slots_for_position,
    _get_slot_priority_for_player,
)


class TestEligibleSlots:
    """Test position eligibility matching."""

    def test_util_accepts_any_position(self):
        """Util slot should accept any position."""
        assert _get_eligible_slots_for_position(["PG"], "Util")
        assert _get_eligible_slots_for_position(["C"], "Util")
        assert _get_eligible_slots_for_position(["SF"], "Util")

    def test_g_slot_accepts_guards(self):
        """G slot should accept PG and SG."""
        assert _get_eligible_slots_for_position(["PG"], "G")
        assert _get_eligible_slots_for_position(["SG"], "G")
        assert not _get_eligible_slots_for_position(["C"], "G")
        assert not _get_eligible_slots_for_position(["SF"], "G")

    def test_f_slot_accepts_forwards(self):
        """F slot should accept SF and PF."""
        assert _get_eligible_slots_for_position(["SF"], "F")
        assert _get_eligible_slots_for_position(["PF"], "F")
        assert not _get_eligible_slots_for_position(["C"], "F")
        assert not _get_eligible_slots_for_position(["PG"], "F")

    def test_specific_position_requires_exact_match(self):
        """Specific position slots require exact match."""
        assert _get_eligible_slots_for_position(["PG"], "PG")
        assert not _get_eligible_slots_for_position(["SG"], "PG")
        assert _get_eligible_slots_for_position(["C"], "C")
        assert not _get_eligible_slots_for_position(["PF"], "C")

    def test_multi_eligible_player(self):
        """Player with multiple eligible positions."""
        dual_eligible = ["PG", "SG"]
        assert _get_eligible_slots_for_position(dual_eligible, "PG")
        assert _get_eligible_slots_for_position(dual_eligible, "SG")
        assert _get_eligible_slots_for_position(dual_eligible, "G")
        assert _get_eligible_slots_for_position(dual_eligible, "Util")
        assert not _get_eligible_slots_for_position(dual_eligible, "C")


class TestSlotPriority:
    """Test slot priority calculation."""

    def test_exact_match_priority(self):
        """Exact position match should have highest priority."""
        assert _get_slot_priority_for_player(["PG"], "PG") == 1
        assert _get_slot_priority_for_player(["C"], "C") == 1

    def test_flex_position_priority(self):
        """Flex positions should have medium priority."""
        assert _get_slot_priority_for_player(["PG"], "G") == 2
        assert _get_slot_priority_for_player(["SG"], "G") == 2
        assert _get_slot_priority_for_player(["SF"], "F") == 2
        assert _get_slot_priority_for_player(["PF"], "F") == 2

    def test_util_priority(self):
        """Util should have lowest priority."""
        assert _get_slot_priority_for_player(["PG"], "Util") == 3
        assert _get_slot_priority_for_player(["C"], "Util") == 3

    def test_ineligible_slot(self):
        """Ineligible slots should have very high priority."""
        assert _get_slot_priority_for_player(["PG"], "C") == 999
        assert _get_slot_priority_for_player(["C"], "PG") == 999


class TestRosterOptimization:
    """Test the main roster optimization function."""

    def test_single_position_player(self):
        """Player with single position eligibility should get that slot."""
        players = [
            {"player_key": "player1", "eligible_positions": ["C"]},
        ]
        league_roster = ["C", "BN"]
        players_with_games = {"player1"}

        result = optimize_roster_positions(players, league_roster, players_with_games)

        assert result["player1"] == "C"

    def test_dual_eligible_player_prefers_specific(self):
        """Dual-eligible player should prefer specific position over flex."""
        players = [
            {"player_key": "player1", "eligible_positions": ["PG", "SG"]},
        ]
        league_roster = ["PG", "G", "BN"]
        players_with_games = {"player1"}

        result = optimize_roster_positions(players, league_roster, players_with_games)

        assert result["player1"] == "PG"

    def test_least_flexible_assigned_first(self):
        """Players with fewer position eligibilities should be assigned first."""
        players = [
            {"player_key": "flexible", "eligible_positions": ["C", "PF"]},
            {"player_key": "restricted", "eligible_positions": ["C"]},
        ]
        league_roster = ["C", "PF", "BN"]
        players_with_games = {"flexible", "restricted"}

        result = optimize_roster_positions(players, league_roster, players_with_games)

        # Restricted player should get C, flexible should get PF
        assert result["restricted"] == "C"
        assert result["flexible"] == "PF"

    def test_util_as_overflow(self):
        """Util slot should be used when specific positions are full."""
        players = [
            {"player_key": "pg1", "eligible_positions": ["PG"]},
            {"player_key": "pg2", "eligible_positions": ["PG"]},
        ]
        league_roster = ["PG", "Util", "BN"]
        players_with_games = {"pg1", "pg2"}

        result = optimize_roster_positions(players, league_roster, players_with_games)

        # One should get PG, other should get Util
        positions = {result["pg1"], result["pg2"]}
        assert "PG" in positions
        assert "Util" in positions

    def test_no_games_assigned_to_bench(self):
        """Players without games should be assigned to BN."""
        players = [
            {"player_key": "active", "eligible_positions": ["PG"]},
            {"player_key": "inactive", "eligible_positions": ["SG"]},
        ]
        league_roster = ["PG", "SG", "BN"]
        players_with_games = {"active"}  # Only active has games

        result = optimize_roster_positions(players, league_roster, players_with_games)

        assert result["active"] == "PG"
        assert result["inactive"] == "BN"

    def test_overflow_to_bench(self):
        """When all active slots are full, excess players go to BN."""
        players = [
            {"player_key": "pg1", "eligible_positions": ["PG"]},
            {"player_key": "pg2", "eligible_positions": ["PG"]},
            {"player_key": "pg3", "eligible_positions": ["PG"]},
        ]
        league_roster = ["PG", "BN"]
        players_with_games = {"pg1", "pg2", "pg3"}

        result = optimize_roster_positions(players, league_roster, players_with_games)

        # One gets PG, others go to BN
        active_count = sum(1 for pos in result.values() if pos != "BN")
        assert active_count == 1
        bench_count = sum(1 for pos in result.values() if pos == "BN")
        assert bench_count == 2

    def test_complex_roster(self):
        """Test with a realistic complex roster."""
        players = [
            {"player_key": "c_only", "eligible_positions": ["C"]},
            {"player_key": "pf_c", "eligible_positions": ["PF", "C"]},
            {"player_key": "sf", "eligible_positions": ["SF"]},
            {"player_key": "pg_sg", "eligible_positions": ["PG", "SG"]},
        ]
        league_roster = ["PG", "SG", "SF", "PF", "C", "G", "F", "Util", "BN", "BN"]
        players_with_games = {"c_only", "pf_c", "sf", "pg_sg"}

        result = optimize_roster_positions(players, league_roster, players_with_games)

        # All players should get active slots
        assert result["c_only"] == "C"
        assert result["pf_c"] == "PF"  # Should use PF to free C for c_only
        assert result["sf"] == "SF"
        # pg_sg could get PG or SG
        assert result["pg_sg"] in ["PG", "SG"]

    def test_inactive_positions_not_used(self):
        """IL and IL+ positions should not be assigned."""
        players = [
            {"player_key": "player1", "eligible_positions": ["PG"]},
        ]
        league_roster = ["IL", "IL+", "BN"]
        players_with_games = {"player1"}

        result = optimize_roster_positions(players, league_roster, players_with_games)

        # Should go to BN, not IL/IL+
        assert result["player1"] == "BN"


class TestGetActivePositions:
    """Test getting active positions from optimized roster."""

    def test_active_positions_excludes_inactive(self):
        """Should exclude BN, IL, IL+."""
        optimized = {
            "player1": "PG",
            "player2": "BN",
            "player3": "IL",
            "player4": "IL+",
            "player5": "C",
        }

        active = get_active_positions(optimized)

        assert "player1" in active
        assert "player5" in active
        assert "player2" not in active
        assert "player3" not in active
        assert "player4" not in active
        assert len(active) == 2

    def test_empty_roster(self):
        """Empty roster should return empty set."""
        active = get_active_positions({})
        assert len(active) == 0

    def test_all_bench(self):
        """All players on bench should return empty set."""
        optimized = {
            "player1": "BN",
            "player2": "BN",
        }

        active = get_active_positions(optimized)

        assert len(active) == 0

