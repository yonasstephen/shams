"""Tests for the composed draft board."""

from __future__ import annotations

from typing import List

import pytest

from tools.draft import recommender, scarcity
from tools.draft.draft_state import DraftPick, DraftState, RosterSlot
from tools.tests.test_draft_scarcity import CATEGORIES, build_state, player


def pool(count: int = 60) -> List:
    """A pool where value decreases with index and ADP tracks it."""
    return [
        player(
            str(i),
            points=2200 - i * 25,
            assists=700 - i * 8,
            blocks=250 - i * 3,
            rank=i,
            adp_=float(i),
        )
        for i in range(1, count + 1)
    ]


@pytest.fixture(name="state")
def state_fixture() -> DraftState:
    """A draft eight picks in, with me on the clock next."""
    picks = [DraftPick(i, str(i + 1), str((i % 4) + 1)) for i in range(8)]
    return build_state(pool(), picks=picks, num_teams=4, rounds=8, current_pick=8)


class TestBoardComposition:
    """The panel's contract."""

    def test_produces_a_headline_and_alternatives(self, state):
        board = recommender.recommend(state)
        assert board.headline is not None
        assert len(board.alternatives) == 3
        assert board.headline.player_id not in {a.player_id for a in board.alternatives}

    def test_headline_has_a_reason(self, state):
        board = recommender.recommend(state)
        assert board.headline.reason

    def test_shortlist_is_ordered_by_score(self, state):
        board = recommender.recommend(state)
        scores = [row.score for row in board.board[:12]]
        assert scores == sorted(scores, reverse=True)

    def test_board_excludes_drafted_players(self, state):
        board = recommender.recommend(state)
        drafted = state.drafted_player_ids
        assert not {row.player_id for row in board.board} & drafted

    def test_every_row_carries_category_detail(self, state):
        board = recommender.recommend(state)
        for row in board.board:
            assert set(row.category_z) == {c.name for c in CATEGORIES}

    def test_reports_draft_position(self, state):
        board = recommender.recommend(state)
        assert board.current_pick == 8
        assert board.picks_until_my_turn == state.picks_until_my_turn()
        # Roster entries keep the player object: drafted players are absent from
        # the board, so the panel has nowhere else to resolve a name from.
        assert [p.player_id for p in board.my_roster] == [
            p.player_id for p in state.my_roster()
        ]
        assert all(p.name for p in board.my_roster)

    def test_includes_scarcity_and_heat_map(self, state):
        board = recommender.recommend(state)
        assert len(board.supply) == len(CATEGORIES)
        assert set(board.heat_map) == {c.name for c in CATEGORIES}

    def test_includes_a_punt_verdict(self, state):
        board = recommender.recommend(state)
        assert board.punt is not None
        assert board.punt_options


class TestRankingBehaviour:
    """Marginal value leads; standings impact nudges."""

    def test_headline_beats_alternatives_on_score(self, state):
        board = recommender.recommend(state)
        for alt in board.alternatives:
            assert board.headline.score >= alt.score

    def test_score_combines_marginal_and_standings(self, state):
        board = recommender.recommend(state)
        row = board.headline
        expected = row.marginal_value + (row.standings_delta or 0.0)
        assert row.score == pytest.approx(expected)

    def test_simulation_noise_cannot_bury_a_better_player(self, state):
        """A large marginal-value edge must survive an adverse standings delta."""
        board = recommender.recommend(state)
        top = board.board[0]
        # One category win is worth 1.0 in score; a 3-z edge cannot be erased.
        assert top.marginal_value >= board.board[1].marginal_value - 1.0

    def test_marginal_value_is_measured_against_your_next_pick(self, state):
        board = recommender.recommend(state)
        # Someone in the pool must be at or below replacement.
        assert min(row.marginal_value for row in board.board) <= 0


class TestReasons:
    """One reason, chosen by what actually changes a pick."""

    def test_urgency_wins_over_everything(self, state):
        board = recommender.recommend(state)
        row = next((r for r in board.board if r.survival is not None and r.survival < 0.35), None)
        if row is not None:
            assert "last" in row.reason.lower()

    def test_supply_crunch_is_called_out(self):
        supply = scarcity.CategorySupply(
            name="assists",
            display_name="AST",
            my_total=-3.0,
            league_mean=0.0,
            league_teams=4,
            elite_remaining=2,
            elite_surviving=0.4,
            teams_below_mean=3,
        )
        rec = recommender.Recommendation(
            player_id="1",
            name="P",
            positions=[],
            nba_team="",
            injury="",
            total_value=1.0,
            marginal_value=1.0,
            category_z={"assists": 2.0},
        )
        reason = recommender._build_reason(rec, {"assists": supply}, set())
        assert "AST" in reason and "elite left" in reason

    def test_punted_categories_never_justify_a_pick(self):
        supply = scarcity.CategorySupply(
            name="assists", display_name="AST", my_total=-3.0, league_mean=0.0, league_teams=4
        )
        rec = recommender.Recommendation(
            player_id="1",
            name="P",
            positions=[],
            nba_team="",
            injury="",
            total_value=1.0,
            marginal_value=1.0,
            category_z={"assists": 3.0},
            standings_delta=0.2,
        )
        reason = recommender._build_reason(rec, {"assists": supply}, {"assists"})
        assert "AST" not in reason


class TestDegenerateInputs:
    """A draft is a bad place to raise."""

    def test_empty_state_returns_an_empty_board(self):
        board = recommender.recommend(DraftState())
        assert board.headline is None
        assert board.board == []

    def test_state_without_categories_returns_empty(self):
        state = build_state(pool(10), picks=[], num_teams=4, rounds=2)
        state.categories = []
        assert recommender.recommend(state).headline is None

    def test_exhausted_pool_returns_empty_board(self):
        players = pool(4)
        picks = [DraftPick(i, str(i + 1), str(i + 1)) for i in range(4)]
        state = build_state(players, picks=picks, num_teams=4, rounds=1, current_pick=4)
        assert recommender.recommend(state).board == []

    def test_summarize_is_safe_on_an_empty_board(self):
        assert not recommender.summarize(recommender.DraftBoard())

    def test_summarize_describes_a_real_board(self, state):
        lines = recommender.summarize(recommender.recommend(state))
        assert any(line.startswith("PICK:") for line in lines)
        assert any(line.startswith("BUILD:") for line in lines)


class TestRosterSlotSizing:
    """Reference pool size follows the league's actual roster depth."""

    def test_bench_spots_count_toward_the_drafted_pool(self, state):
        state.roster_slots = [RosterSlot("Util", 4), RosterSlot("BN", 6)]
        assert state.roster_size == 10
        board = recommender.recommend(state)
        assert board.headline is not None
