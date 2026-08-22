"""Learn the baseline's mistakes.

Marcel is a fixed formula, so its errors are not random — it systematically
misses players whose role is changing, and role change is visible in features
the formula ignores: minutes trend, experience, durability, a team switch. This
fits a small model to that error and adds the correction back.

**Why gradient-boosted stumps written out longhand, rather than scikit-learn.**
Two reasons. The serving path must stay dependency-light — the backend reads a
finished CSV and no model ever runs during a draft — and adding numpy plus
scikit-learn to lock a dependency for one offline script is a poor trade. More
importantly the sample is small: roughly 500 usable players per season, so a
few thousand rows total against a handful of features. Depth-one trees with
heavy shrinkage are the right capacity for that; a full boosting library would
mostly give more ways to overfit.

Whether any of this earns its place is decided by
:mod:`tools.projections.backtest`, not by it existing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from tools.projections.history import SeasonLine
from tools.projections.marcel import ProjectedLine

logger = logging.getLogger(__name__)

#: Stats the correction is learned for.
CORRECTED_STATS = (
    "points",
    "rebounds",
    "assists",
    "steals",
    "blocks",
    "turnovers",
    "threes",
    "fgm",
    "fga",
    "ftm",
    "fta",
)

#: Boosting rounds. Small, because the signal is weak and the sample is not big.
ROUNDS = 40
#: Shrinkage. Low, for the same reason.
LEARNING_RATE = 0.08
#: A split must leave at least this many players on each side to be considered.
MIN_LEAF = 30
#: Correction is capped at this fraction of the baseline prediction, so a
#: misfit model can nudge a projection but never invent a different player.
MAX_CORRECTION = 0.25

FEATURE_NAMES = (
    "experience",
    "projected_mpg",
    "mpg_trend",
    "games_last",
    "changed_teams",
    "start_rate",
    "baseline_value",
    "seasons_of_history",
)


@dataclass
class Stump:
    """A depth-one regression tree."""

    feature: int
    threshold: float
    left: float
    right: float

    def predict(self, features: Sequence[float]) -> float:
        """Prediction for one feature vector."""
        return self.left if features[self.feature] <= self.threshold else self.right


@dataclass
class BoostedModel:
    """An additive ensemble of stumps for one stat."""

    stat: str
    base: float = 0.0
    stumps: List[Stump] = field(default_factory=list)
    learning_rate: float = LEARNING_RATE

    def predict(self, features: Sequence[float]) -> float:
        """Predicted residual for one feature vector."""
        total = self.base
        for stump in self.stumps:
            total += self.learning_rate * stump.predict(features)
        return total


def build_features(
    player_history: Sequence[SeasonLine],
    projected: ProjectedLine,
    experience: Optional[int],
) -> List[float]:
    """Feature vector describing a player's situation.

    Args:
        player_history: Seasons most recent first.
        projected: The baseline projection being corrected.
        experience: Seasons since debut, if known.

    Returns:
        Features in :data:`FEATURE_NAMES` order.
    """
    latest = player_history[0]
    previous = player_history[1] if len(player_history) > 1 else None

    mpg_trend = 0.0
    if previous is not None and previous.minutes_per_game > 0:
        mpg_trend = latest.minutes_per_game - previous.minutes_per_game

    return [
        float(experience if experience is not None else 5),
        projected.minutes_per_game,
        mpg_trend,
        float(latest.games_played),
        1.0 if latest.changed_teams else 0.0,
        latest.start_rate,
        projected.per_game.get("points", 0.0),
        float(len(player_history)),
    ]


def _best_stump(
    rows: Sequence[Sequence[float]], targets: Sequence[float]
) -> Optional[Stump]:
    """Find the depth-one split that most reduces squared error."""
    count = len(rows)
    if count < 2 * MIN_LEAF:
        return None

    total = sum(targets)
    best: Optional[Stump] = None
    best_gain = 0.0

    for feature in range(len(FEATURE_NAMES)):
        # Bind `feature` as a default so the closure cannot pick up a later
        # loop value; sorted() runs eagerly, but the binding makes that explicit.
        order = sorted(range(count), key=lambda i, f=feature: rows[i][f])
        left_sum = 0.0
        for position in range(count - 1):
            index = order[position]
            left_sum += targets[index]
            left_count = position + 1
            right_count = count - left_count
            if left_count < MIN_LEAF or right_count < MIN_LEAF:
                continue
            # A split between equal values is not a split.
            if rows[order[position]][feature] == rows[order[position + 1]][feature]:
                continue

            right_sum = total - left_sum
            # Reduction in squared error from splitting here.
            gain = (left_sum**2) / left_count + (right_sum**2) / right_count
            if gain > best_gain:
                best_gain = gain
                threshold = (
                    rows[order[position]][feature] + rows[order[position + 1]][feature]
                ) / 2.0
                best = Stump(
                    feature=feature,
                    threshold=threshold,
                    left=left_sum / left_count,
                    right=right_sum / right_count,
                )

    return best


def fit(
    rows: Sequence[Sequence[float]],
    targets: Sequence[float],
    stat: str,
    rounds: int = ROUNDS,
) -> BoostedModel:
    """Fit a boosted stump ensemble to residuals.

    Args:
        rows: Feature vectors.
        targets: Residuals (actual minus baseline), same order.
        stat: Which stat this model corrects.
        rounds: Boosting rounds.

    Returns:
        The fitted model.
    """
    model = BoostedModel(stat=stat)
    if not rows:
        return model

    model.base = sum(targets) / len(targets)
    working = [target - model.base for target in targets]

    for _ in range(rounds):
        stump = _best_stump(rows, working)
        if stump is None:
            break
        model.stumps.append(stump)
        for index, features in enumerate(rows):
            working[index] -= model.learning_rate * stump.predict(features)

    return model


def apply_correction(
    projected: ProjectedLine,
    features: Sequence[float],
    models: Dict[str, BoostedModel],
) -> ProjectedLine:
    """Add learned corrections to a baseline projection.

    Corrections are clamped to :data:`MAX_CORRECTION` of the baseline so a
    poorly-fit model degrades the projection slightly rather than replacing it
    with something unrecognizable.
    """
    for stat, model in models.items():
        baseline = projected.per_game.get(stat)
        if baseline is None:
            continue
        correction = model.predict(features)
        limit = abs(baseline) * MAX_CORRECTION
        correction = max(-limit, min(limit, correction))
        projected.per_game[stat] = max(baseline + correction, 0.0)

    # Percentages follow the corrected volume.
    fga = projected.per_game.get("fga", 0.0)
    fta = projected.per_game.get("fta", 0.0)
    projected.per_game["fg_pct"] = (
        projected.per_game.get("fgm", 0.0) / fga if fga else 0.0
    )
    projected.per_game["ft_pct"] = (
        projected.per_game.get("ftm", 0.0) / fta if fta else 0.0
    )
    return projected


def train(
    training_rows: Sequence[Tuple[Sequence[float], Dict[str, float]]],
    stats: Sequence[str] = CORRECTED_STATS,
) -> Dict[str, BoostedModel]:
    """Fit one model per stat.

    Args:
        training_rows: Pairs of (features, residuals-by-stat).
        stats: Stats to correct.

    Returns:
        Stat -> fitted model.
    """
    if not training_rows:
        return {}

    rows = [features for features, _ in training_rows]
    models: Dict[str, BoostedModel] = {}
    for stat in stats:
        targets = [residuals.get(stat, 0.0) for _, residuals in training_rows]
        models[stat] = fit(rows, targets, stat)
    return models
