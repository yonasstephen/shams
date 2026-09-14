"""Punt-aware category valuation for the draftable pool.

Why this is not :func:`tools.player.player_stats.compute_9cat_zscore`:

- That function hardcodes nine categories and takes a ``PlayerStats`` object.
  Draft leagues configure their own categories, which arrive in the store.
- More importantly, it z-scores **raw** ``fg_pct``. For fantasy valuation that is
  wrong: a 40% shooter on 2 attempts a game barely moves your team's percentage,
  while a 40% shooter on 20 attempts wrecks it. Percentage categories have to be
  weighted by volume — makes above what an average-efficiency player would have
  produced *on the same attempts*.

The in-season function stays as it is; this is the draft-day valuation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Set

from tools.draft.draft_state import DraftPlayer
from tools.draft.stat_ids import RATIO_STATS, StatCategory

# Below this many attempts a percentage contribution is noise, and dividing by a
# near-zero denominator produces nonsense.
_MIN_ATTEMPTS = 1e-6


@dataclass
class ValuationContext:
    """League-relative baselines used to score every player.

    Attributes:
        categories: The league's scoring categories.
        means: Per-category mean of the scored quantity across the reference pool.
        stddevs: Per-category standard deviation across the reference pool.
        ratio_baselines: League-average percentage for each ratio category, computed
            as total makes over total attempts (not an average of percentages).
        pool_size: How many players formed the reference pool.
    """

    categories: List[StatCategory]
    means: Dict[str, float] = field(default_factory=dict)
    stddevs: Dict[str, float] = field(default_factory=dict)
    ratio_baselines: Dict[str, float] = field(default_factory=dict)
    pool_size: int = 0


@dataclass
class ValuedPlayer:
    """A player scored against the league's categories."""

    player: DraftPlayer
    category_z: Dict[str, float] = field(default_factory=dict)

    def total(self, punt: Optional[Set[str]] = None) -> float:
        """Summed z-score across categories, excluding any that are punted.

        Args:
            punt: Category names to ignore.

        Returns:
            Total value under that punt build.
        """
        punted = punt or frozenset()
        return sum(z for name, z in self.category_z.items() if name not in punted)

    @property
    def player_id(self) -> str:
        """Yahoo player id."""
        return self.player.player_id


def _scored_quantity(
    player: DraftPlayer, category: StatCategory, ratio_baselines: Dict[str, float]
) -> float:
    """The quantity a category is scored on for one player.

    Counting categories score the projected total. Ratio categories score
    *makes above baseline* — how many extra makes the player produces relative to
    a league-average shooter taking the same number of attempts. That keeps
    volume in the valuation, which raw percentage throws away.
    """
    stats = player.projected

    if category.name in RATIO_STATS:
        makes_key, attempts_key = RATIO_STATS[category.name]
        attempts = stats.get(attempts_key, 0.0)
        if attempts <= _MIN_ATTEMPTS:
            return 0.0
        makes = stats.get(makes_key, 0.0)
        baseline = ratio_baselines.get(category.name, 0.0)
        return makes - attempts * baseline

    return stats.get(category.name, 0.0)


def _mean_and_stddev(values: Sequence[float]) -> tuple:
    """Population mean and standard deviation."""
    if not values:
        return 0.0, 1.0
    mean = sum(values) / len(values)
    if len(values) < 2:
        return mean, 1.0
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return mean, math.sqrt(variance) or 1.0


def select_reference_pool(
    players: Iterable[DraftPlayer], pool_size: int
) -> List[DraftPlayer]:
    """Pick the players whose distribution defines "average".

    Scoring against all ~660 rostered NBA players would make replacement-level
    scrubs look average and compress everyone real into a narrow band. The
    distribution that matters is the players who actually get drafted, so the
    pool is the top ``pool_size`` by Yahoo's projected rank.

    Args:
        players: Candidate players; those without a projection are dropped.
        pool_size: How many players to keep, typically teams x roster size.

    Returns:
        The reference pool, best first.
    """
    projected = [p for p in players if p.has_projection]
    projected.sort(key=lambda p: (p.projected_rank is None, p.projected_rank or 0))
    return projected[:pool_size] if pool_size > 0 else projected


def build_context(
    players: Iterable[DraftPlayer],
    categories: Sequence[StatCategory],
    pool_size: int,
) -> ValuationContext:
    """Compute league baselines from a reference pool.

    Args:
        players: All players to consider for the pool.
        categories: The league's scoring categories.
        pool_size: Reference pool size (teams x roster size).

    Returns:
        The context used to score individual players.
    """
    pool = select_reference_pool(players, pool_size)
    context = ValuationContext(categories=list(categories), pool_size=len(pool))
    if not pool:
        return context

    # Ratio baselines first: they feed the scored quantity for those categories.
    for category in categories:
        if category.name not in RATIO_STATS:
            continue
        makes_key, attempts_key = RATIO_STATS[category.name]
        total_makes = sum(p.projected.get(makes_key, 0.0) for p in pool)
        total_attempts = sum(p.projected.get(attempts_key, 0.0) for p in pool)
        context.ratio_baselines[category.name] = (
            total_makes / total_attempts if total_attempts > _MIN_ATTEMPTS else 0.0
        )

    for category in categories:
        values = [
            _scored_quantity(player, category, context.ratio_baselines) for player in pool
        ]
        mean, stddev = _mean_and_stddev(values)
        context.means[category.name] = mean
        context.stddevs[category.name] = stddev

    return context


def value_player(player: DraftPlayer, context: ValuationContext) -> ValuedPlayer:
    """Score one player against the league baselines.

    Categories where less is better (turnovers, read from ``sort_order``) have
    their z inverted, so a positive z always means "helps you".
    """
    category_z: Dict[str, float] = {}
    for category in context.categories:
        quantity = _scored_quantity(player, category, context.ratio_baselines)
        mean = context.means.get(category.name, 0.0)
        stddev = context.stddevs.get(category.name, 1.0) or 1.0
        z = (quantity - mean) / stddev
        category_z[category.name] = z if category.higher_is_better else -z
    return ValuedPlayer(player=player, category_z=category_z)


def value_players(
    players: Iterable[DraftPlayer], context: ValuationContext
) -> List[ValuedPlayer]:
    """Score many players against the same baselines."""
    return [value_player(player, context) for player in players]


def rank_by_value(
    valued: Iterable[ValuedPlayer], punt: Optional[Set[str]] = None
) -> List[ValuedPlayer]:
    """Order players by total value under a punt build, best first."""
    return sorted(valued, key=lambda v: v.total(punt), reverse=True)


def replacement_value(
    valued: Sequence[ValuedPlayer],
    index: int,
    punt: Optional[Set[str]] = None,
) -> float:
    """Value of the replacement-level player.

    Args:
        valued: Available players, any order.
        index: How deep into the available pool replacement sits — normally the
            number of picks left before your next turn, or the number of roster
            spots left across the league.
        punt: Categories being punted.

    Returns:
        The total value at that depth, or the worst available value if the pool
        is shallower than ``index``.
    """
    if not valued:
        return 0.0
    ranked = rank_by_value(valued, punt)
    position = min(max(index, 0), len(ranked) - 1)
    return ranked[position].total(punt)


def marginal_values(
    valued: Sequence[ValuedPlayer],
    replacement: float,
    punt: Optional[Set[str]] = None,
) -> Dict[str, float]:
    """Value above replacement for each player.

    Raw total value ranks players; value *above replacement* is what should drive
    a pick, because it measures what you actually gain over the alternative you
    could still get later.

    Args:
        valued: Available players.
        replacement: Replacement-level total, from :func:`replacement_value`.
        punt: Categories being punted.

    Returns:
        Mapping of player id to value above replacement.
    """
    return {player.player_id: player.total(punt) - replacement for player in valued}
