"""Marcel-style baseline projections.

The Marcel method is deliberately the dumbest forecast worth taking seriously:
a weighted average of recent seasons, regressed toward the league mean by sample
size, scaled by projected playing time. It exists to be the bar a fancier model
has to clear, and it is famously hard to beat by much.

Three pieces:

1. **Weighted per-36 rates.** Recent seasons count more (5/4/3), and each season
   is weighted by the minutes behind it — a 200-minute season is far weaker
   evidence than a 2,500-minute one.
2. **Regression to the mean.** A rate computed off few minutes is mostly noise,
   so it is pulled toward the league rate in proportion to how little evidence
   supports it. :data:`REGRESSION_MINUTES` sets how much evidence counts as
   "enough".
3. **Playing time.** Rates are per-36; the projection is rate x projected
   minutes. Minutes are the dominant term in any fantasy projection and the part
   a statistical model handles worst, which is why they are separated out and
   can be overridden by hand.

Age is approximated by experience (seasons since debut), which costs one API
call rather than several hundred. True age would be better; see
:mod:`tools.projections.experience`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from tools.projections.history import SeasonLine

#: Season weights, most recent first. Classic Marcel proportions.
SEASON_WEIGHTS = (5.0, 4.0, 3.0)

#: How many minutes of evidence it takes for a rate to stand on its own. Below
#: this the projection leans on the league rate instead.
#:
#: Swept over 200-2500 against two held-out seasons. Heavier regression
#: monotonically improves MAE and monotonically *hurts* rank correlation, so
#: there is no setting that is best at both. 1000 sits near the MAE optimum
#: while keeping ranking above the naive forecast on 2025-26:
#:
#:     reg    2025-26 MAE / r      2024-25 MAE / r
#:     200    0.8762 / 0.7944      0.7860 / 0.8513
#:     1000   0.8643 / 0.7893      0.7789 / 0.8493
#:     2500   0.8661 / 0.7789      0.7843 / 0.8447
#:     naive  0.9297 / 0.7850      0.7817 / 0.8522
REGRESSION_MINUTES = 1000.0

#: Minutes regress toward this baseline for players with little recent play.
REPLACEMENT_MINUTES_PER_GAME = 12.0
REGRESSION_GAMES = 25.0

#: Games a healthy player is projected for. Availability is its own forecasting
#: problem; this is the anchor that per-player history adjusts.
BASELINE_GAMES = 68.0

#: Rate stats projected per 36 minutes.
RATE_STATS = (
    "fgm",
    "fga",
    "ftm",
    "fta",
    "threes",
    "points",
    "rebounds",
    "assists",
    "steals",
    "blocks",
    "turnovers",
)

#: Experience curve: multiplier on projected minutes by seasons of experience.
#: Young players grow into roles, veterans lose them. Deliberately gentle — this
#: is a proxy for age, not age itself.
_EXPERIENCE_CURVE = {
    0: 1.12,
    1: 1.10,
    2: 1.06,
    3: 1.03,
    4: 1.01,
}
_VETERAN_DECLINE_START = 11
_VETERAN_DECLINE_PER_SEASON = 0.02


@dataclass
class ProjectedLine:
    """A player's projected season."""

    nba_id: int
    name: str
    games: float = 0.0
    minutes_per_game: float = 0.0
    #: Per-game counting stats and percentages.
    per_game: Dict[str, float] = field(default_factory=dict)
    #: Seasons of history behind the projection, most recent first.
    seasons_used: List[str] = field(default_factory=list)
    experience: Optional[int] = None

    @property
    def minutes(self) -> float:
        """Projected total minutes."""
        return self.games * self.minutes_per_game

    def totals(self) -> Dict[str, float]:
        """Projected season totals, the shape Yahoo's draft store uses."""
        out: Dict[str, float] = {"games_played": self.games}
        for stat in RATE_STATS:
            out[stat] = self.per_game.get(stat, 0.0) * self.games
        # Percentages are ratios and are recomputed, never multiplied out.
        out["fg_pct"] = _safe_ratio(out.get("fgm", 0.0), out.get("fga", 0.0))
        out["ft_pct"] = _safe_ratio(out.get("ftm", 0.0), out.get("fta", 0.0))
        return out


def _safe_ratio(numerator: float, denominator: float) -> float:
    """Ratio guarding against a zero denominator."""
    return numerator / denominator if denominator else 0.0


def league_rates(lines: Sequence[SeasonLine]) -> Dict[str, float]:
    """Per-36 league rates, pooled over players with meaningful minutes.

    Pooled totals rather than an average of player rates, so a fringe player's
    small sample cannot swing the baseline.
    """
    qualified = [line for line in lines if line.minutes >= 300]
    total_minutes = sum(line.minutes for line in qualified)
    if total_minutes <= 0:
        return {stat: 0.0 for stat in RATE_STATS}

    return {
        stat: sum(line.totals.get(stat, 0.0) for line in qualified) * 36.0 / total_minutes
        for stat in RATE_STATS
    }


def _experience_multiplier(experience: Optional[int]) -> float:
    """Minutes multiplier from seasons of experience."""
    if experience is None:
        return 1.0
    if experience in _EXPERIENCE_CURVE:
        return _EXPERIENCE_CURVE[experience]
    if experience >= _VETERAN_DECLINE_START:
        decline = (experience - _VETERAN_DECLINE_START + 1) * _VETERAN_DECLINE_PER_SEASON
        return max(1.0 - decline, 0.7)
    return 1.0


def _weighted_history(
    player_history: Sequence[SeasonLine],
) -> tuple:
    """Combine a player's recent seasons into weighted totals and minutes.

    Args:
        player_history: The player's seasons, most recent first.

    Returns:
        Tuple of (weighted stat totals, weighted minutes).
    """
    totals: Dict[str, float] = {stat: 0.0 for stat in RATE_STATS}
    minutes = 0.0

    for index, line in enumerate(player_history[: len(SEASON_WEIGHTS)]):
        weight = SEASON_WEIGHTS[index]
        minutes += weight * line.minutes
        for stat in RATE_STATS:
            totals[stat] += weight * line.totals.get(stat, 0.0)

    return totals, minutes


def _project_minutes(
    player_history: Sequence[SeasonLine], experience: Optional[int]
) -> tuple:
    """Project games played and minutes per game.

    Both regress toward a replacement-level baseline for players with thin
    recent history, then take the experience adjustment.
    """
    weighted_mpg = 0.0
    weighted_games = 0.0
    weight_total = 0.0
    games_weight_total = 0.0

    for index, line in enumerate(player_history[: len(SEASON_WEIGHTS)]):
        weight = SEASON_WEIGHTS[index]
        # Minutes per game weighted by how many games back it up.
        weighted_mpg += weight * line.minutes_per_game * line.games_played
        weight_total += weight * line.games_played
        weighted_games += weight * line.games_played
        games_weight_total += weight

    if weight_total <= 0:
        return 0.0, 0.0

    raw_mpg = weighted_mpg / weight_total
    mpg = (weighted_mpg + REGRESSION_GAMES * REPLACEMENT_MINUTES_PER_GAME) / (
        weight_total + REGRESSION_GAMES
    )
    # Keep the regression from dragging established starters down too far.
    mpg = max(mpg, raw_mpg * 0.85)

    games = weighted_games / games_weight_total if games_weight_total else 0.0
    games = (games + BASELINE_GAMES) / 2.0

    multiplier = _experience_multiplier(experience)
    return min(games, 82.0), mpg * multiplier


def project_player(
    player_history: Sequence[SeasonLine],
    rates: Dict[str, float],
    experience: Optional[int] = None,
) -> Optional[ProjectedLine]:
    """Project one player from his recent seasons.

    Args:
        player_history: Seasons most recent first. Only the first three count.
        rates: League per-36 rates for regression.
        experience: Seasons since debut, if known.

    Returns:
        The projection, or None when there is no usable history.
    """
    if not player_history:
        return None

    totals, weighted_minutes = _weighted_history(player_history)
    if weighted_minutes <= 0:
        return None

    games, mpg = _project_minutes(player_history, experience)
    if games <= 0 or mpg <= 0:
        return None

    line = ProjectedLine(
        nba_id=player_history[0].nba_id,
        name=player_history[0].name,
        games=games,
        minutes_per_game=mpg,
        seasons_used=[entry.season for entry in player_history[: len(SEASON_WEIGHTS)]],
        experience=experience,
    )

    for stat in RATE_STATS:
        # Regressed per-36 rate: observed evidence blended with the league rate,
        # weighted by how many minutes support it.
        observed = totals.get(stat, 0.0) * 36.0
        prior = rates.get(stat, 0.0) * REGRESSION_MINUTES
        rate_per_36 = (observed + prior) / (weighted_minutes + REGRESSION_MINUTES)
        line.per_game[stat] = rate_per_36 * mpg / 36.0

    line.per_game["fg_pct"] = _safe_ratio(line.per_game["fgm"], line.per_game["fga"])
    line.per_game["ft_pct"] = _safe_ratio(line.per_game["ftm"], line.per_game["fta"])
    return line


def project_season(
    seasons: Dict[str, Dict[int, SeasonLine]],
    prior_seasons: Sequence[str],
    experience: Optional[Dict[int, int]] = None,
) -> Dict[int, ProjectedLine]:
    """Project every player with usable history.

    Args:
        seasons: Season string -> player id -> that player's line.
        prior_seasons: Seasons to draw on, **most recent first**.
        experience: Optional player id -> seasons of experience.

    Returns:
        Player id -> projection.
    """
    ordered = [season for season in prior_seasons if season in seasons]
    if not ordered:
        return {}

    # Baselines come from the most recent season, which best reflects how the
    # league currently plays.
    rates = league_rates(list(seasons[ordered[0]].values()))

    player_ids = {pid for season in ordered for pid in seasons[season]}
    projections: Dict[int, ProjectedLine] = {}
    experience = experience or {}

    for player_id in player_ids:
        player_history = [
            seasons[season][player_id] for season in ordered if player_id in seasons[season]
        ]
        projected = project_player(
            player_history, rates, experience.get(player_id)
        )
        if projected is not None:
            projections[player_id] = projected

    return projections
