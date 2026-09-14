"""Tests for draft-state parsing against a real Yahoo draft-room payload."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.draft import stat_ids
from tools.draft.draft_state import parse_draft_state

FIXTURE = Path(__file__).parent / "fixtures" / "draft_state_sample.json"


@pytest.fixture(name="payload")
def payload_fixture() -> dict:
    """The captured draft-room payload."""
    with open(FIXTURE, "r", encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture(name="state")
def state_fixture(payload: dict):
    """Parsed draft state."""
    return parse_draft_state(payload)


class TestStatIdDecoding:
    """Yahoo keys its stat blobs by numeric id."""

    def test_decodes_named_stats(self, state):
        lebron = state.players["3704"]
        assert lebron.projected["points"] == 1221
        assert lebron.projected["rebounds"] == 373
        assert lebron.projected["assists"] == 419
        assert lebron.projected["turnovers"] == 180
        assert lebron.projected["games_played"] == 66

    def test_keeps_shooting_volume(self, state):
        """FGA/FGM/FTA/FTM are needed for volume-weighted percentages."""
        lebron = state.players["3704"]
        assert lebron.projected["fga"] == 907
        assert lebron.projected["fgm"] == 463
        assert lebron.projected["fta"] == 278
        assert lebron.projected["ftm"] == 210

    def test_percentages_reconcile_with_volume(self, state):
        """Verifies the id mapping itself: FGM/FGA must equal the FG% field."""
        for player in state.players.values():
            if not player.has_projection:
                continue
            attempts = player.projected["fga"]
            if attempts:
                derived = player.projected["fgm"] / attempts
                assert derived == pytest.approx(player.projected["fg_pct"], abs=0.002)

    def test_ignores_unknown_ids(self):
        assert stat_ids.parse_stat_blob({"999": "5", "12": "10"}) == {"points": 10.0}

    def test_handles_placeholders(self):
        parsed = stat_ids.parse_stat_blob({"12": "-", "15": "", "16": None, "17": "3"})
        assert parsed["points"] == 0.0
        assert parsed["steals"] == 3.0


class TestScoringCategories:
    """Categories come from the league, not a hardcoded 9-cat list."""

    def test_drops_display_only_categories(self, state):
        names = [c.name for c in state.categories]
        assert "games_played" not in names
        assert len(state.categories) == 9

    def test_turnovers_read_as_lower_is_better(self, state):
        turnovers = next(c for c in state.categories if c.name == "turnovers")
        assert turnovers.higher_is_better is False

    def test_other_categories_are_higher_is_better(self, state):
        for category in state.categories:
            if category.name != "turnovers":
                assert category.higher_is_better is True

    def test_ratio_categories_pull_in_their_volume(self, state):
        required = stat_ids.required_stat_names(state.categories)
        for name in ("fgm", "fga", "ftm", "fta"):
            assert name in required


class TestPlayerPool:
    """Inactive players carry an all-zero projected line."""

    def test_zero_projection_is_missing_not_zero(self, state):
        jeff_green = state.players["4247"]
        assert jeff_green.injury == "NA"
        assert jeff_green.has_projection is False

    def test_available_pool_excludes_unprojected_players(self, state):
        available_ids = {p.player_id for p in state.available_players()}
        assert "4247" not in available_ids

    def test_available_pool_excludes_drafted_players(self, state):
        available_ids = {p.player_id for p in state.available_players()}
        # Durant (4244) and LeBron (3704) are already picked in the fixture.
        assert "4244" not in available_ids
        assert "3704" not in available_ids
        assert "4245" in available_ids

    def test_can_opt_into_unprojected_players(self, state):
        relaxed = {p.player_id for p in state.available_players(require_projection=False)}
        assert "4247" in relaxed

    def test_positions_are_pre_expanded_to_flex(self, state):
        """Yahoo already expands eligibility, which roster_optimizer consumes."""
        assert state.players["3704"].positions == ["SF", "PF", "F", "Util"]
        assert "C" in state.players["4245"].positions

    def test_per_game_conversion(self, state):
        lebron = state.players["3704"]
        per_game = lebron.projected_per_game()
        assert per_game["points"] == pytest.approx(1221 / 66)
        # Percentages are rates already and must not be divided by games.
        assert per_game["fg_pct"] == pytest.approx(0.510)

    def test_per_game_empty_without_games(self, state):
        assert state.players["4247"].projected_per_game() == {}


class TestDraftStructure:
    """The published pick order makes survival questions exact."""

    def test_league_metadata(self, state):
        assert state.num_teams == 14
        assert state.is_mock is True
        assert state.is_auction is False
        assert state.season == "2026-27"
        assert state.pick_seconds == 30
        assert state.my_team_id == "6"

    def test_rounds_derived_from_order(self, state):
        assert len(state.pick_order) == 182
        assert state.total_rounds == 13

    def test_roster_slots(self, state):
        assert state.roster_size == 13
        assert state.active_slot_count == 10

    def test_my_upcoming_picks_follow_the_snake(self, state):
        upcoming = state.my_upcoming_picks()
        # Round 2 reverses, so team 6's round-2 pick is index 22 — already past
        # at currentPick 24. The next is round 3, index 28+5 = 33.
        assert upcoming[0] == 33
        assert state.picks_until_my_turn() == 33 - 24

    def test_not_my_turn(self, state):
        assert state.current_team_id == "4"
        assert state.is_my_turn() is False

    def test_roster_lookup(self, state):
        my_roster = state.my_roster()
        assert [p.player_id for p in my_roster] == ["3704"]
        assert [p.player_id for p in state.roster("14")] == ["4244"]


class TestMalformedPayloads:
    """A draft is a bad place to raise."""

    def test_empty_payload_yields_empty_state(self):
        state = parse_draft_state({})
        assert state.players == {}
        assert state.picks == []
        assert state.picks_until_my_turn() is None

    def test_picks_missing_fields_are_skipped(self):
        state = parse_draft_state(
            {"picks": [{"id": "1"}, {"id": "2", "playerId": "9", "teamId": "3"}]}
        )
        assert len(state.picks) == 1

    def test_players_without_ids_are_skipped(self):
        state = parse_draft_state({"players": [{"fname": "No"}, {"id": "1", "fname": "Yes"}]})
        assert list(state.players) == ["1"]


class TestManualPicks:
    """The fallback for when the adapter misses a pick."""

    def test_manual_pick_leaves_the_pool(self, payload):
        payload["manualPicks"] = ["4245"]
        state = parse_draft_state(payload)
        assert "4245" not in {p.player_id for p in state.available_players()}

    def test_manual_pick_has_no_owning_team(self, payload):
        """We know he is gone, not who took him — so no roster gets his stats."""
        payload["manualPicks"] = ["4245"]
        state = parse_draft_state(payload)
        manual = next(p for p in state.picks if p.player_id == "4245")
        assert manual.team_id == ""
        for team_id in state.teams:
            assert "4245" not in {p.player_id for p in state.roster(team_id)}

    def test_manual_pick_duplicating_a_real_one_is_ignored(self, payload):
        before = len(parse_draft_state(payload).picks)
        payload["manualPicks"] = ["4244"]  # already drafted in the fixture
        assert len(parse_draft_state(payload).picks) == before

    def test_manual_picks_do_not_collide_with_real_pick_numbers(self, payload):
        payload["manualPicks"] = ["4245", "4246"]
        state = parse_draft_state(payload)
        numbers = [p.pick_number for p in state.picks]
        assert len(numbers) == len(set(numbers))

    def test_blank_entries_are_skipped(self, payload):
        payload["manualPicks"] = ["", "4245"]
        state = parse_draft_state(payload)
        assert sum(1 for p in state.picks if not p.team_id) == 1
