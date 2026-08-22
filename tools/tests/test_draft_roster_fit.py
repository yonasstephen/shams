"""Tests for roster-slot fit and schedule signal."""

from __future__ import annotations

import pytest

from tools.draft import roster_fit, schedule_value, simulator, value_model
from tools.draft.draft_state import DraftPick, DraftPlayer, RosterSlot
from tools.tests.test_draft_scarcity import build_state, player

# A realistic small layout: one of each, two centres, one Util, two bench.
SLOTS = [
    RosterSlot("PG", 1),
    RosterSlot("SF", 1),
    RosterSlot("C", 2),
    RosterSlot("Util", 1),
    RosterSlot("BN", 2),
]


def pos_player(pid: str, positions) -> DraftPlayer:
    """A player with given eligibility and an ordinary projected line."""
    return DraftPlayer(
        player_id=pid,
        first_name="P",
        last_name=pid,
        positions=list(positions),
        projected={"games_played": 70.0, "points": 1200.0},
    )


class TestStartableSlots:
    """Position eligibility, not just value, decides who plays."""

    def test_balanced_roster_starts_everyone_it_can(self):
        roster = [
            pos_player("pg", ["PG", "G", "Util"]),
            pos_player("sf", ["SF", "F", "Util"]),
            pos_player("c1", ["C", "Util"]),
            pos_player("c2", ["C", "Util"]),
            pos_player("u", ["SG", "G", "Util"]),
        ]
        starters = roster_fit.startable_players(roster, SLOTS)
        assert len(starters) == 5

    def test_surplus_centres_get_benched(self):
        """Five centres into a two-C league: only C, C and Util can play."""
        roster = [pos_player(f"c{i}", ["C", "Util"]) for i in range(5)]
        starters = roster_fit.startable_players(roster, SLOTS)
        assert len(starters) == 3

    def test_bench_weight_applied_to_the_squeezed_out(self):
        roster = [pos_player(f"c{i}", ["C", "Util"]) for i in range(5)]
        weights = roster_fit.contribution_weights(roster, SLOTS)
        assert sorted(weights.values()) == pytest.approx(
            [roster_fit.BENCH_WEIGHT, roster_fit.BENCH_WEIGHT, 1.0, 1.0, 1.0]
        )

    def test_ranking_decides_who_wins_a_contested_slot(self):
        """Better players should take the slot when eligibility is equal."""
        roster = [pos_player(f"c{i}", ["C", "Util"]) for i in range(5)]
        ranks = {f"c{i}": i for i in range(5)}
        starters = roster_fit.startable_players(roster, SLOTS, ranks)
        assert "c0" in starters
        assert "c4" not in starters

    def test_no_slots_means_no_benching(self):
        roster = [pos_player("a", ["C"]), pos_player("b", ["C"])]
        weights = roster_fit.contribution_weights(roster, [])
        assert set(weights.values()) == {1.0}

    def test_empty_roster_is_safe(self):
        assert roster_fit.startable_players([], SLOTS) == set()
        assert roster_fit.contribution_weights([], SLOTS) == {}

    def test_slot_layout_expands_counts(self):
        assert roster_fit.slot_layout(SLOTS) == [
            "PG", "SF", "C", "C", "Util", "BN", "BN",
        ]


class TestPositionalGaps:
    """What you still need, as opposed to what is merely good."""

    def test_empty_roster_needs_every_active_slot(self):
        gaps = roster_fit.positional_gaps([], SLOTS)
        assert gaps == {"PG": 1, "SF": 1, "C": 2, "Util": 1}

    def test_filled_slots_disappear_from_the_gaps(self):
        roster = [pos_player("pg", ["PG", "G", "Util"])]
        gaps = roster_fit.positional_gaps(roster, SLOTS)
        assert "PG" not in gaps
        assert gaps["C"] == 2

    def test_bench_slots_are_never_reported_as_gaps(self):
        assert "BN" not in roster_fit.positional_gaps([], SLOTS)


class TestSimulatorHonoursRosterFit:
    """The correction has to change the standings, not just exist."""

    def _state_with(self, my_positions):
        """Build a draft where my team already holds players of given positions.

        Everyone in the pool is Util-eligible so the only positional constraint
        under test is the one seeded onto my roster.
        """
        # Stats must vary or every z-score is exactly zero and no weighting can
        # show an effect. Values depend only on the index, so both scenarios seed
        # identical production onto my team and differ purely in position.
        pool = [
            player(
                str(i),
                points=2200 - i * 40,
                assists=650 - i * 12,
                blocks=260 - i * 5,
                rank=i,
                adp_=float(i),
            )
            for i in range(1, 30)
        ]
        for entry in pool:
            entry.positions = ["SG", "G", "Util"]
        for index, positions in enumerate(my_positions):
            pool[index].positions = list(positions)
        picks = [DraftPick(i, str(i + 1), "1") for i in range(len(my_positions))]
        state = build_state(pool, picks=picks, num_teams=4, rounds=6, current_pick=len(my_positions))
        state.roster_slots = SLOTS
        ctx = value_model.build_context(state.players.values(), state.categories, pool_size=29)
        valued = value_model.value_players(state.players.values(), ctx)
        by_id = {v.player_id: v for v in valued}
        available = [by_id[p.player_id] for p in state.available_players()]
        return state, available, by_id

    def test_lopsided_roster_scores_below_a_balanced_one(self):
        """Identical production, different shape — the balanced team wins.

        Five centres overflow a 2xC + Util layout, so two of them get benched
        while the balanced roster starts all five.
        """
        spread = [
            ["PG", "G", "Util"],
            ["SF", "F", "Util"],
            ["C", "Util"],
            ["C", "Util"],
            ["SG", "G", "Util"],
        ]
        balanced, avail_b, by_id_b = self._state_with(spread)
        lopsided, avail_l, by_id_l = self._state_with([["C", "Util"]] * 5)

        b_totals = simulator.simulate(balanced, avail_b, by_id_b).totals["1"]
        l_totals = simulator.simulate(lopsided, avail_l, by_id_l).totals["1"]
        assert sum(b_totals.values()) > sum(l_totals.values())

    def test_overflow_positions_are_the_cause(self):
        """Confirm the mechanism directly, not just the aggregate effect."""
        lopsided, _, _ = self._state_with([["C", "Util"]] * 5)
        weights = roster_fit.contribution_weights(lopsided.my_roster(), SLOTS)
        assert sorted(weights.values()).count(roster_fit.BENCH_WEIGHT) == 2

    def test_simulation_still_fills_every_pick(self):
        state, available, by_id = self._state_with([["C", "Util"]])
        standings = simulator.simulate(state, available, by_id)
        for team_id in state.teams:
            assert len(standings.additions[team_id]) >= 1


class TestScheduleValue:
    """Bounded, and neutral when the season is not cached."""

    def test_unknown_team_yields_an_empty_schedule(self):
        result = schedule_value.load_team_schedule("ZZZ", "2025-26")
        assert result.is_known is False
        assert result.games_per_week == 0.0

    def test_adjustments_are_neutral_without_data(self):
        schedules = {
            "AAA": schedule_value.TeamSchedule("AAA"),
            "BBB": schedule_value.TeamSchedule("BBB"),
        }
        assert set(schedule_value.adjustments(schedules).values()) == {1.0}

    def test_adjustments_stay_within_bounds(self):
        schedules = {
            "AAA": schedule_value.TeamSchedule("AAA", games=82, weeks=25, heavy_weeks=20),
            "BBB": schedule_value.TeamSchedule("BBB", games=82, weeks=25, heavy_weeks=2),
            "CCC": schedule_value.TeamSchedule("CCC", games=82, weeks=25, heavy_weeks=11),
        }
        values = schedule_value.adjustments(schedules)
        for value in values.values():
            assert abs(value - 1.0) <= schedule_value.MAX_ADJUSTMENT + 1e-9

    def test_heavier_schedule_scores_higher(self):
        schedules = {
            "AAA": schedule_value.TeamSchedule("AAA", games=82, weeks=25, heavy_weeks=20),
            "BBB": schedule_value.TeamSchedule("BBB", games=82, weeks=25, heavy_weeks=2),
        }
        values = schedule_value.adjustments(schedules)
        assert values["AAA"] > values["BBB"]

    def test_teams_without_schedules_are_left_neutral(self):
        schedules = {
            "AAA": schedule_value.TeamSchedule("AAA", games=82, weeks=25, heavy_weeks=20),
            "BBB": schedule_value.TeamSchedule("BBB", games=82, weeks=25, heavy_weeks=2),
            "ZZZ": schedule_value.TeamSchedule("ZZZ"),
        }
        assert schedule_value.adjustments(schedules)["ZZZ"] == 1.0

    def test_heavy_week_share(self):
        schedule = schedule_value.TeamSchedule("AAA", games=80, weeks=20, heavy_weeks=5)
        assert schedule.heavy_week_share == pytest.approx(0.25)
        assert schedule.games_per_week == pytest.approx(4.0)
