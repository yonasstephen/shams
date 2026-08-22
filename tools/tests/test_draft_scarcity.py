"""Tests for scarcity analysis, draft simulation, and punt detection."""

from __future__ import annotations

from typing import Dict, List, Optional

import pytest

from tools.draft import punt_detector, scarcity, simulator, value_model
from tools.draft.draft_state import (
    DraftPick,
    DraftPlayer,
    DraftState,
    DraftTeam,
    RosterSlot,
)
from tools.draft.stat_ids import StatCategory

CATEGORIES = [
    StatCategory(12, "points", "PTS", 1, False),
    StatCategory(16, "assists", "AST", 1, False),
    StatCategory(18, "blocks", "BLK", 1, False),
]


def player(pid: str, points: float, assists: float, blocks: float, rank: int, adp_: Optional[float]):
    """Build a player with a projected line and market data."""
    return DraftPlayer(
        player_id=pid,
        first_name="P",
        last_name=pid,
        projected_rank=rank,
        average_pick=adp_,
        projected={
            "games_played": 70.0,
            "points": points,
            "assists": assists,
            "blocks": blocks,
        },
    )


def snake(num_teams: int, rounds: int) -> List[str]:
    """Snake pick order as a flat list of team ids by pick index."""
    order: List[str] = []
    for round_index in range(rounds):
        teams = range(1, num_teams + 1)
        order.extend(str(t) for t in (teams if round_index % 2 == 0 else reversed(list(teams))))
    return order


def build_state(
    players: List[DraftPlayer],
    picks: List[DraftPick],
    num_teams: int = 4,
    rounds: int = 5,
    current_pick: int = 0,
    my_team_id: str = "1",
) -> DraftState:
    """Assemble a draft state for testing."""
    order = snake(num_teams, rounds)
    return DraftState(
        num_teams=num_teams,
        my_team_id=my_team_id,
        current_pick=current_pick,
        current_team_id=order[current_pick] if current_pick < len(order) else "",
        teams={
            str(i): DraftTeam(str(i), f"team{i}", is_me=str(i) == my_team_id)
            for i in range(1, num_teams + 1)
        },
        players={p.player_id: p for p in players},
        picks=picks,
        pick_order=order,
        roster_slots=[RosterSlot("Util", 4), RosterSlot("BN", 1)],
        categories=CATEGORIES,
    )


def value(state: DraftState):
    """Score every player and split into (available, by_id)."""
    ctx = value_model.build_context(
        state.players.values(), state.categories, pool_size=len(state.players)
    )
    valued_all = value_model.value_players(state.players.values(), ctx)
    by_id: Dict[str, value_model.ValuedPlayer] = {v.player_id: v for v in valued_all}
    available = [by_id[p.player_id] for p in state.available_players()]
    return available, by_id


class TestSimulator:
    """Playing out the remaining picks."""

    @pytest.fixture(name="setup")
    def setup_fixture(self):
        players = [
            player(str(i), points=2000 - i * 50, assists=300, blocks=100, rank=i, adp_=float(i))
            for i in range(1, 25)
        ]
        state = build_state(players, picks=[], num_teams=4, rounds=5)
        available, by_id = value(state)
        return state, available, by_id

    def test_every_team_fills_its_picks(self, setup):
        state, available, by_id = setup
        standings = simulator.simulate(state, available, by_id)
        for team_id in state.teams:
            assert len(standings.additions[team_id]) == 5

    def test_no_player_is_drafted_twice(self, setup):
        state, available, by_id = setup
        standings = simulator.simulate(state, available, by_id)
        drafted = [pid for ids in standings.additions.values() for pid in ids]
        assert len(drafted) == len(set(drafted))

    def test_forced_pick_is_honoured(self, setup):
        state, available, by_id = setup
        standings = simulator.simulate(state, available, by_id, forced_pick="20")
        assert "20" in standings.additions[state.my_team_id]
        assert len(standings.additions[state.my_team_id]) == 5

    def test_existing_picks_are_counted(self):
        players = [
            player(str(i), points=1000, assists=300, blocks=100, rank=i, adp_=float(i))
            for i in range(1, 25)
        ]
        picks = [DraftPick(pick_number=0, player_id="1", team_id="1")]
        state = build_state(players, picks=picks, current_pick=1)
        available, by_id = value(state)
        standings = simulator.simulate(state, available, by_id)
        # Four more picks in rounds 2-5, plus the one already made.
        assert len(standings.additions["1"]) == 4

    def test_category_wins_bounded_by_category_count(self, setup):
        state, available, by_id = setup
        standings = simulator.simulate(state, available, by_id)
        wins = standings.category_wins(state.my_team_id)
        assert 0.0 <= wins <= len(CATEGORIES)

    def test_taking_a_better_player_does_not_hurt(self, setup):
        """Sanity: forcing the best available should not beat out worse options."""
        state, available, by_id = setup
        impacts = simulator.impact_of(state, available, by_id, ["1", "24"])
        best = next(i for i in impacts if i.player_id == "1")
        worst = next(i for i in impacts if i.player_id == "24")
        assert best.delta >= worst.delta

    def test_unknown_team_returns_zero_wins(self, setup):
        state, available, by_id = setup
        standings = simulator.simulate(state, available, by_id)
        assert standings.category_wins("nope") == 0.0


class TestScarcityBoard:
    """Supply, demand and runway per category."""

    @pytest.fixture(name="setup")
    def setup_fixture(self):
        # Assist specialists are scarce: only three of the twenty players have
        # meaningful assists, and one is already gone.
        players = []
        for i in range(1, 21):
            assists = 800 if i in (2, 5, 9) else 120
            players.append(
                player(str(i), points=1200, assists=assists, blocks=100, rank=i, adp_=float(i))
            )
        picks = [
            DraftPick(0, "2", "2"),  # an assist source, taken by an opponent
            DraftPick(1, "1", "1"),  # my pick: no assists
        ]
        state = build_state(players, picks=picks, num_teams=4, rounds=5, current_pick=2)
        available, by_id = value(state)
        return state, scarcity.analyze(state, available, by_id), by_id

    def test_counts_elite_sources_remaining(self, setup):
        _, board, _ = setup
        assists = next(s for s in board if s.name == "assists")
        assert assists.elite_remaining == 2

    def test_detects_my_weakness(self, setup):
        state, board, _ = setup
        assists = next(s for s in board if s.name == "assists")
        assert assists.is_weakness is True
        assert assists.my_total < assists.league_mean

    def test_ranks_me_against_the_league(self, setup):
        _, board, _ = setup
        assists = next(s for s in board if s.name == "assists")
        assert 1 <= assists.my_rank <= assists.league_teams

    def test_urgent_categories_sort_first(self, setup):
        _, board, _ = setup
        assert board[0].deficit < 0

    def test_crunch_rises_as_supply_falls(self, setup):
        _, board, _ = setup
        assists = next(s for s in board if s.name == "assists")
        points = next(s for s in board if s.name == "points")
        assert assists.crunch > points.crunch

    def test_survivors_never_exceed_supply(self, setup):
        _, board, _ = setup
        for supply in board:
            assert supply.elite_surviving <= supply.elite_remaining + 1e-9

    def test_heat_map_covers_every_category(self, setup):
        _, board, _ = setup
        heat = scarcity.heat_map(board)
        assert set(heat) == {c.name for c in CATEGORIES}

    def test_summary_is_readable(self, setup):
        _, board, _ = setup
        assert "elite left" in board[0].summary() or "no elite" in board[0].summary()


class TestPuntDetector:
    """A punt must earn its place by simulation, not by vibes."""

    def _lopsided_state(self):
        """My roster is hopeless at blocks; the pool rewards ignoring it."""
        players = []
        for i in range(1, 41):
            # Big men: elite blocks, poor assists. Guards: the reverse.
            if i % 2 == 0:
                pts, ast, blk = 1100, 100, 260
            else:
                pts, ast, blk = 1400, 600, 15
            players.append(player(str(i), pts, ast, blk, rank=i, adp_=float(i)))

        # I already own two guards; opponents took the top bigs.
        picks = [
            DraftPick(0, "2", "2"),
            DraftPick(1, "4", "3"),
            DraftPick(2, "6", "4"),
            DraftPick(3, "1", "1"),
            DraftPick(4, "3", "1"),
        ]
        state = build_state(players, picks=picks, num_teams=4, rounds=8, current_pick=5)
        available, by_id = value(state)
        board = scarcity.analyze(state, available, by_id)
        return state, available, by_id, board

    def test_baseline_is_always_included(self):
        state, available, by_id, board = self._lopsided_state()
        verdicts = punt_detector.evaluate(state, available, by_id, board)
        assert any(not v.categories for v in verdicts)

    def test_verdicts_are_sorted_by_wins(self):
        state, available, by_id, board = self._lopsided_state()
        verdicts = punt_detector.evaluate(state, available, by_id, board)
        wins = [v.category_wins for v in verdicts]
        assert wins == sorted(wins, reverse=True)

    def test_gain_is_relative_to_not_punting(self):
        state, available, by_id, board = self._lopsided_state()
        verdicts = punt_detector.evaluate(state, available, by_id, board)
        no_punt = next(v for v in verdicts if not v.categories)
        assert no_punt.gain == pytest.approx(0.0)
        for verdict in verdicts:
            assert verdict.baseline_wins == pytest.approx(no_punt.category_wins)

    def test_candidates_are_categories_i_am_behind_in(self):
        _, _, _, board = self._lopsided_state()
        candidates = punt_detector.candidate_punts(board)
        for name in candidates:
            supply = next(s for s in board if s.name == name)
            assert supply.deficit < 0

    def test_best_build_ignores_marginal_gains(self):
        """A punt worth 0.01 category wins must not be recommended."""
        verdicts = [
            punt_detector.PuntVerdict(frozenset({"blocks"}), 5.01, 5.0),
            punt_detector.PuntVerdict(frozenset(), 5.0, 5.0),
        ]
        assert punt_detector.best_build(verdicts).categories == frozenset()

    def test_best_build_commits_on_a_real_gain(self):
        verdicts = [
            punt_detector.PuntVerdict(frozenset({"blocks"}), 5.9, 5.0),
            punt_detector.PuntVerdict(frozenset(), 5.0, 5.0),
        ]
        assert punt_detector.best_build(verdicts).categories == frozenset({"blocks"})

    def test_best_build_handles_no_verdicts(self):
        assert punt_detector.best_build([]).categories == frozenset()

    def test_respects_the_build_cap(self):
        state, available, by_id, board = self._lopsided_state()
        verdicts = punt_detector.evaluate(state, available, by_id, board, max_builds=3)
        assert len(verdicts) <= 3

    def test_summary_mentions_the_category(self):
        verdict = punt_detector.PuntVerdict(frozenset({"blocks"}), 5.9, 5.0)
        assert "BLK" in verdict.summary({"blocks": "BLK"})
        assert "+0.90" in verdict.summary({"blocks": "BLK"})
