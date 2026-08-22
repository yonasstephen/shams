"""Tests for draft-day player valuation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.draft import value_model
from tools.draft.draft_state import DraftPlayer, parse_draft_state
from tools.draft.stat_ids import StatCategory

FIXTURE = Path(__file__).parent / "fixtures" / "draft_state_sample.json"


def make_player(player_id: str, **stats) -> DraftPlayer:
    """Build a player with a projected line, defaulting a full season."""
    projected = {"games_played": 70.0}
    projected.update(stats)
    return DraftPlayer(
        player_id=player_id,
        first_name="P",
        last_name=player_id,
        projected_rank=int(player_id),
        projected=projected,
    )


def category(name: str, stat_id: int = 1, sort_order: int = 1) -> StatCategory:
    """Build a scoring category."""
    return StatCategory(
        stat_id=stat_id,
        name=name,
        display_name=name.upper(),
        sort_order=sort_order,
        is_display_only=False,
    )


class TestVolumeWeightedPercentages:
    """The reason this module exists rather than reusing compute_9cat_zscore."""

    def _context_and_values(self, players):
        cats = [category("fg_pct", stat_id=5)]
        ctx = value_model.build_context(players, cats, pool_size=len(players))
        return ctx, {v.player_id: v for v in value_model.value_players(players, ctx)}

    def test_baseline_is_pooled_makes_over_pooled_attempts(self):
        players = [
            make_player("1", fgm=500.0, fga=1000.0, fg_pct=0.5),
            make_player("2", fgm=300.0, fga=1000.0, fg_pct=0.3),
        ]
        ctx, _ = self._context_and_values(players)
        # 800 makes / 2000 attempts = .40, not the .40 average of .50 and .30
        # by coincidence -- check a case where they differ.
        assert ctx.ratio_baselines["fg_pct"] == pytest.approx(0.4)

    def test_baseline_is_not_the_mean_of_percentages(self):
        players = [
            make_player("1", fgm=90.0, fga=100.0, fg_pct=0.9),
            make_player("2", fgm=100.0, fga=1000.0, fg_pct=0.1),
        ]
        ctx, _ = self._context_and_values(players)
        # Mean of percentages would be .50; volume-weighted is 190/1100 = .173.
        assert ctx.ratio_baselines["fg_pct"] == pytest.approx(190 / 1100)

    def test_high_volume_efficiency_beats_low_volume_efficiency(self):
        """Same percentage, different attempts: volume must decide."""
        players = [
            make_player("1", fgm=600.0, fga=1000.0, fg_pct=0.6),  # efficient, high volume
            make_player("2", fgm=60.0, fga=100.0, fg_pct=0.6),  # efficient, low volume
            make_player("3", fgm=400.0, fga=1000.0, fg_pct=0.4),  # inefficient, high volume
        ]
        _, valued = self._context_and_values(players)
        assert valued["1"].category_z["fg_pct"] > valued["2"].category_z["fg_pct"]
        assert valued["2"].category_z["fg_pct"] > valued["3"].category_z["fg_pct"]

    def test_low_volume_shooter_lands_near_neutral(self):
        """A tiny sample should barely move the needle either way."""
        players = [
            make_player("1", fgm=600.0, fga=1000.0, fg_pct=0.6),
            make_player("2", fgm=400.0, fga=1000.0, fg_pct=0.4),
            make_player("3", fgm=1.0, fga=2.0, fg_pct=0.5),
        ]
        _, valued = self._context_and_values(players)
        big = abs(valued["1"].category_z["fg_pct"])
        assert abs(valued["3"].category_z["fg_pct"]) < big / 2

    def test_zero_attempts_is_neutral_not_a_crash(self):
        players = [
            make_player("1", fgm=600.0, fga=1000.0, fg_pct=0.6),
            make_player("2", fgm=400.0, fga=1000.0, fg_pct=0.4),
            make_player("3", fgm=0.0, fga=0.0, fg_pct=0.0),
        ]
        ctx, valued = self._context_and_values(players)
        assert valued["3"].category_z["fg_pct"] == pytest.approx(
            (0.0 - ctx.means["fg_pct"]) / ctx.stddevs["fg_pct"]
        )


class TestCategoryDirection:
    """Direction comes from sort_order, not a hardcoded turnovers case."""

    def test_lower_is_better_inverts_the_z(self):
        players = [
            make_player("1", turnovers=100.0),
            make_player("2", turnovers=300.0),
        ]
        cats = [category("turnovers", stat_id=19, sort_order=0)]
        ctx = value_model.build_context(players, cats, pool_size=2)
        valued = {v.player_id: v for v in value_model.value_players(players, ctx)}
        assert valued["1"].category_z["turnovers"] > 0
        assert valued["2"].category_z["turnovers"] < 0

    def test_higher_is_better_does_not_invert(self):
        players = [make_player("1", points=2000.0), make_player("2", points=500.0)]
        cats = [category("points", stat_id=12)]
        ctx = value_model.build_context(players, cats, pool_size=2)
        valued = {v.player_id: v for v in value_model.value_players(players, ctx)}
        assert valued["1"].category_z["points"] > 0
        assert valued["2"].category_z["points"] < 0


class TestPuntAwareness:
    """Punting must re-rank the pool, not just hide a column."""

    def _setup(self):
        # A specialist who is elite at assists and terrible at blocks, versus a
        # big who is the reverse. Punting should flip their order.
        players = [
            make_player("1", assists=800.0, blocks=20.0, points=1200.0),
            make_player("2", assists=100.0, blocks=200.0, points=1200.0),
            make_player("3", assists=400.0, blocks=100.0, points=1200.0),
        ]
        cats = [category("assists", 16), category("blocks", 18), category("points", 12)]
        ctx = value_model.build_context(players, cats, pool_size=3)
        return value_model.value_players(players, ctx)

    def test_punting_a_category_changes_the_ranking(self):
        valued = self._setup()
        no_punt = [v.player_id for v in value_model.rank_by_value(valued)]
        punt_blocks = [
            v.player_id for v in value_model.rank_by_value(valued, punt={"blocks"})
        ]
        assert no_punt != punt_blocks
        assert punt_blocks[0] == "1"

    def test_punting_excludes_the_category_from_the_total(self):
        valued = self._setup()
        player = valued[0]
        assert player.total(punt={"blocks"}) == pytest.approx(
            player.total() - player.category_z["blocks"]
        )

    def test_punting_everything_is_zero(self):
        valued = self._setup()
        all_cats = set(valued[0].category_z)
        assert valued[0].total(punt=all_cats) == pytest.approx(0.0)


class TestReplacementLevel:
    """Value above replacement, not raw value, should drive a pick."""

    def _valued(self):
        players = [make_player(str(i), points=2000.0 - i * 100) for i in range(1, 11)]
        cats = [category("points", 12)]
        ctx = value_model.build_context(players, cats, pool_size=10)
        return value_model.value_players(players, ctx)

    def test_replacement_tracks_depth(self):
        valued = self._valued()
        shallow = value_model.replacement_value(valued, index=1)
        deep = value_model.replacement_value(valued, index=8)
        assert shallow > deep

    def test_replacement_clamps_past_the_pool(self):
        valued = self._valued()
        assert value_model.replacement_value(valued, index=999) == pytest.approx(
            value_model.replacement_value(valued, index=9)
        )

    def test_marginal_value_is_relative_to_replacement(self):
        valued = self._valued()
        replacement = value_model.replacement_value(valued, index=5)
        marginals = value_model.marginal_values(valued, replacement)
        best = max(marginals.values())
        assert best == pytest.approx(valued[0].total() - replacement)
        # The replacement player himself is worth nothing above replacement.
        assert min(abs(v) for v in marginals.values()) == pytest.approx(0.0, abs=1e-9)

    def test_empty_pool_is_zero(self):
        assert value_model.replacement_value([], index=3) == 0.0


class TestReferencePool:
    """Scoring against the whole NBA would compress everyone real together."""

    def test_pool_is_limited_to_draftable_players(self):
        players = [make_player(str(i), points=2000.0 - i * 10) for i in range(1, 101)]
        pool = value_model.select_reference_pool(players, pool_size=20)
        assert len(pool) == 20
        assert pool[0].player_id == "1"

    def test_pool_excludes_players_without_projections(self):
        good = make_player("1", points=1000.0)
        empty = DraftPlayer(player_id="2", first_name="No", last_name="Line", projected={})
        pool = value_model.select_reference_pool([good, empty], pool_size=10)
        assert [p.player_id for p in pool] == ["1"]

    def test_smaller_pool_widens_the_spread(self):
        """A tighter reference pool should not collapse the z distribution."""
        players = [make_player(str(i), points=2000.0 - i * 10) for i in range(1, 101)]
        cats = [category("points", 12)]
        wide = value_model.build_context(players, cats, pool_size=100)
        narrow = value_model.build_context(players, cats, pool_size=20)
        assert narrow.stddevs["points"] < wide.stddevs["points"]


class TestAgainstRealFixture:
    """End-to-end on the captured draft payload."""

    @pytest.fixture(name="state")
    def state_fixture(self):
        with open(FIXTURE, "r", encoding="utf-8") as handle:
            return parse_draft_state(json.load(handle))

    def test_values_every_available_player(self, state):
        available = state.available_players()
        ctx = value_model.build_context(
            state.players.values(), state.categories, pool_size=state.num_teams * state.roster_size
        )
        valued = value_model.value_players(available, ctx)
        assert len(valued) == len(available)
        assert all(len(v.category_z) == 9 for v in valued)

    def test_ranking_is_stable_and_ordered(self, state):
        ctx = value_model.build_context(
            state.players.values(), state.categories, pool_size=state.num_teams * state.roster_size
        )
        valued = value_model.value_players(state.available_players(), ctx)
        ranked = value_model.rank_by_value(valued)
        totals = [v.total() for v in ranked]
        assert totals == sorted(totals, reverse=True)
