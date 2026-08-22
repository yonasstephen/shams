"""Backtest the projection model against what actually happened.

This is the gate. A projection model is easy to write and hard to justify, so
nothing ships on the strength of looking reasonable — it has to beat a naive
forecast on held-out seasons.

The naive baseline is "last season, repeated". That sounds trivially weak, but
in basketball it is genuinely strong: most players do roughly what they did last
year. A model that cannot beat it is adding nothing.

Two things are measured, because they answer different questions:

- **MAE per category** — how wrong is a typical projection, in the units of the
  stat. This is what matters for computing totals.
- **Rank correlation** — does the model order players correctly. This is what
  matters for a draft, where you only ever choose between players.

Usage:
    pipenv run python -m tools.projections.backtest --test 2025-26
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from tools.projections import history, marcel, residual
from tools.projections.history import SeasonLine
from tools.projections.marcel import ProjectedLine

#: Categories scored in the comparison. Percentages are volume-weighted, so they
#: are judged on makes and attempts rather than the ratio itself.
COMPARED = (
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

#: Only judge players who actually played enough to matter in a draft.
MIN_TEST_MINUTES = 500.0


@dataclass
class Metrics:
    """Accuracy of one forecast against one actual season."""

    label: str
    players: int = 0
    mae: Dict[str, float] = field(default_factory=dict)
    spearman: Dict[str, float] = field(default_factory=dict)
    games_mae: float = 0.0
    minutes_mae: float = 0.0

    @property
    def mean_mae(self) -> float:
        """Average MAE across categories, for a single headline number."""
        return sum(self.mae.values()) / len(self.mae) if self.mae else 0.0

    @property
    def mean_spearman(self) -> float:
        """Average rank correlation across categories."""
        return (
            sum(self.spearman.values()) / len(self.spearman) if self.spearman else 0.0
        )


def _spearman(pairs: Sequence[tuple]) -> float:
    """Spearman rank correlation for (predicted, actual) pairs."""
    count = len(pairs)
    if count < 3:
        return 0.0

    def ranks(values: Sequence[float]) -> List[float]:
        order = sorted(range(len(values)), key=lambda i: values[i])
        result = [0.0] * len(values)
        index = 0
        while index < len(order):
            # Average ranks across ties so equal values do not bias the result.
            end = index
            while end + 1 < len(order) and values[order[end + 1]] == values[order[index]]:
                end += 1
            average = (index + end) / 2.0 + 1.0
            for position in range(index, end + 1):
                result[order[position]] = average
            index = end + 1
        return result

    predicted_ranks = ranks([p for p, _ in pairs])
    actual_ranks = ranks([a for _, a in pairs])

    mean_p = sum(predicted_ranks) / count
    mean_a = sum(actual_ranks) / count
    numerator = sum(
        (predicted_ranks[i] - mean_p) * (actual_ranks[i] - mean_a) for i in range(count)
    )
    denom_p = sum((predicted_ranks[i] - mean_p) ** 2 for i in range(count)) ** 0.5
    denom_a = sum((actual_ranks[i] - mean_a) ** 2 for i in range(count)) ** 0.5
    if denom_p == 0 or denom_a == 0:
        return 0.0
    # Clamp: floating-point error can push a perfect correlation just past 1.0,
    # and a correlation outside [-1, 1] is never a meaningful result.
    return max(-1.0, min(1.0, numerator / (denom_p * denom_a)))


def _actual_per_game(line: SeasonLine) -> Dict[str, float]:
    """Per-game actuals for the compared categories."""
    return {stat: line.per_game(stat) for stat in COMPARED}


def evaluate(
    predictions: Dict[int, Dict[str, float]],
    actuals: Dict[int, SeasonLine],
    label: str,
    predicted_minutes: Optional[Dict[int, tuple]] = None,
) -> Metrics:
    """Score a set of per-game predictions against an actual season.

    Args:
        predictions: Player id -> per-game predicted stats.
        actuals: Player id -> actual season line.
        label: Name for the forecast being scored.
        predicted_minutes: Optional player id -> (games, minutes per game).

    Returns:
        The metrics.
    """
    metrics = Metrics(label=label)

    shared = [
        player_id
        for player_id in predictions
        if player_id in actuals and actuals[player_id].minutes >= MIN_TEST_MINUTES
    ]
    metrics.players = len(shared)
    if not shared:
        return metrics

    for stat in COMPARED:
        errors = []
        pairs = []
        for player_id in shared:
            predicted = predictions[player_id].get(stat, 0.0)
            actual = actuals[player_id].per_game(stat)
            errors.append(abs(predicted - actual))
            pairs.append((predicted, actual))
        metrics.mae[stat] = sum(errors) / len(errors)
        metrics.spearman[stat] = _spearman(pairs)

    if predicted_minutes:
        game_errors, minute_errors = [], []
        for player_id in shared:
            if player_id not in predicted_minutes:
                continue
            games, mpg = predicted_minutes[player_id]
            game_errors.append(abs(games - actuals[player_id].games_played))
            minute_errors.append(abs(mpg - actuals[player_id].minutes_per_game))
        if game_errors:
            metrics.games_mae = sum(game_errors) / len(game_errors)
            metrics.minutes_mae = sum(minute_errors) / len(minute_errors)

    return metrics


def naive_forecast(previous: Dict[int, SeasonLine]) -> Dict[int, Dict[str, float]]:
    """"Last season, repeated" — the bar the model has to clear."""
    return {pid: _actual_per_game(line) for pid, line in previous.items()}


def marcel_forecast(
    projections: Dict[int, ProjectedLine]
) -> Dict[int, Dict[str, float]]:
    """Per-game predictions from Marcel projections."""
    return {pid: dict(line.per_game) for pid, line in projections.items()}


def _training_rows(
    train_season: str,
    train_priors: Sequence[str],
    loaded: Dict[str, Dict[int, SeasonLine]],
    experience: Dict[int, int],
) -> List[tuple]:
    """Build residual training data from a season the test never sees.

    The baseline is fit on ``train_priors`` and scored against ``train_season``;
    the gap between them is what the residual model learns. Using a season
    earlier than the test season is what keeps the evaluation honest.
    """
    available = [s for s in train_priors if s in loaded]
    if train_season not in loaded or not available:
        return []

    projections = marcel.project_season(
        {s: loaded[s] for s in available}, available, experience=experience
    )
    actuals = loaded[train_season]

    rows = []
    for player_id, projected in projections.items():
        actual = actuals.get(player_id)
        if actual is None or actual.minutes < MIN_TEST_MINUTES:
            continue
        player_history = [loaded[s][player_id] for s in available if player_id in loaded[s]]
        if not player_history:
            continue
        features = residual.build_features(
            player_history, projected, experience.get(player_id)
        )
        residuals = {
            stat: actual.per_game(stat) - projected.per_game.get(stat, 0.0)
            for stat in residual.CORRECTED_STATS
        }
        rows.append((features, residuals))
    return rows


def run(
    test_season: str,
    prior_seasons: Sequence[str],
    use_experience: bool = True,
    with_residual: bool = False,
    train_season: Optional[str] = None,
    train_priors: Optional[Sequence[str]] = None,
) -> List[Metrics]:
    """Backtest every forecast against a held-out season.

    Args:
        test_season: The season to predict and score against.
        prior_seasons: Seasons available to the model, most recent first. Must
            not include ``test_season``.
        use_experience: Apply the experience-based minutes adjustment.
        with_residual: Also evaluate the residual-corrected model.
        train_season: Season the residual model is fitted against. Must differ
            from ``test_season``.
        train_priors: Seasons the residual's baseline is built from.

    Returns:
        Metrics for each forecast.
    """
    if test_season in prior_seasons:
        raise ValueError(f"{test_season} cannot be both training and test data")

    needed = [test_season, *prior_seasons]
    if with_residual and train_season:
        needed += [train_season, *(train_priors or [])]
    loaded = history.load_seasons(sorted(set(needed)))
    actuals = loaded.get(test_season) or {}
    if not actuals:
        raise ValueError(f"No cached box scores for {test_season}")

    experience = {}
    if use_experience:
        from tools.projections.experience import experience_map

        experience = experience_map(test_season)

    projections = marcel.project_season(
        {season: loaded[season] for season in prior_seasons if season in loaded},
        prior_seasons,
        experience=experience,
    )

    results = [
        evaluate(
            naive_forecast(loaded.get(prior_seasons[0], {})),
            actuals,
            label=f"naive ({prior_seasons[0]} repeated)",
        ),
        evaluate(
            marcel_forecast(projections),
            actuals,
            label="marcel",
            predicted_minutes={
                pid: (line.games, line.minutes_per_game)
                for pid, line in projections.items()
            },
        ),
    ]

    if with_residual and train_season:
        if train_season == test_season:
            raise ValueError("residual training season cannot be the test season")
        training = _training_rows(
            train_season, train_priors or [], loaded, experience
        )
        if not training:
            raise ValueError("no residual training data available")

        models = residual.train(training)
        corrected: Dict[int, Dict[str, float]] = {}
        for player_id, projected in projections.items():
            player_history = [
                loaded[s][player_id] for s in prior_seasons
                if s in loaded and player_id in loaded[s]
            ]
            if not player_history:
                continue
            features = residual.build_features(
                player_history, projected, experience.get(player_id)
            )
            # Correct a copy: the baseline result must stay comparable.
            clone = marcel.ProjectedLine(
                nba_id=projected.nba_id,
                name=projected.name,
                games=projected.games,
                minutes_per_game=projected.minutes_per_game,
                per_game=dict(projected.per_game),
                seasons_used=list(projected.seasons_used),
                experience=projected.experience,
            )
            corrected[player_id] = dict(
                residual.apply_correction(clone, features, models).per_game
            )

        results.append(
            evaluate(corrected, actuals, label=f"marcel+residual ({len(training)} rows)")
        )

    return results


def _format(results: Sequence[Metrics]) -> str:
    """Render a comparison table."""
    lines = []
    header = f"{'category':<12}" + "".join(f"{m.label:>26}" for m in results)
    lines.append(header)
    lines.append("-" * len(header))

    for stat in COMPARED:
        row = f"{stat:<12}"
        for metrics in results:
            row += f"{metrics.mae.get(stat, 0):>12.3f} r={metrics.spearman.get(stat, 0):>10.3f}"
        lines.append(row)

    lines.append("-" * len(header))
    summary = f"{'MEAN':<12}"
    for metrics in results:
        summary += f"{metrics.mean_mae:>12.3f} r={metrics.mean_spearman:>10.3f}"
    lines.append(summary)
    lines.append("")
    for metrics in results:
        detail = f"{metrics.label}: {metrics.players} players"
        if metrics.games_mae:
            detail += f", games MAE {metrics.games_mae:.1f}, mpg MAE {metrics.minutes_mae:.1f}"
        lines.append(detail)

    best = min(results, key=lambda m: m.mean_mae)
    lines.append("")
    lines.append(f"Lowest mean MAE: {best.label}")
    ranked = max(results, key=lambda m: m.mean_spearman)
    lines.append(f"Best rank correlation: {ranked.label}")
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point."""
    parser = argparse.ArgumentParser(description="Backtest projection models.")
    parser.add_argument("--test", required=True, help="Season to predict, e.g. 2025-26")
    parser.add_argument(
        "--priors",
        nargs="+",
        required=True,
        help="Seasons available to the model, most recent first",
    )
    parser.add_argument(
        "--no-experience", action="store_true", help="Skip the experience adjustment"
    )
    parser.add_argument(
        "--residual", action="store_true", help="Also evaluate the residual model"
    )
    parser.add_argument("--train", help="Season the residual model is fitted against")
    parser.add_argument(
        "--train-priors", nargs="+", help="Seasons the residual's baseline uses"
    )
    args = parser.parse_args(argv)

    results = run(
        args.test,
        args.priors,
        use_experience=not args.no_experience,
        with_residual=args.residual,
        train_season=args.train,
        train_priors=args.train_priors,
    )
    print(f"\nBacktest: predicting {args.test} from {', '.join(args.priors)}\n")
    print(_format(results))
    return 0


if __name__ == "__main__":
    sys.exit(main())
