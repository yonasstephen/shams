"""Decide whether to punt a category, and which one.

Static punt tools let you tick a box and re-rank. This one reads the build
already emerging from your picks, then *tests* each candidate punt by finishing
the draft in simulation and counting categories won.

The objective is total expected category wins across **all** categories,
including the punted one. That is the honest measure: punting concedes a
category, so it only pays if the players it frees you to take win back more
elsewhere. A punt that doesn't clear the no-punt baseline is reported as such.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Set

from tools.draft.draft_state import DraftState
from tools.draft.scarcity import CategorySupply
from tools.draft.simulator import simulate
from tools.draft.value_model import ValuedPlayer

#: Only consider punting categories you are already behind in by this much.
_WEAKNESS_THRESHOLD = 0.0
#: How many single-category punts to consider pairing.
_PAIR_CANDIDATES = 3
#: Below this gain in expected category wins, a punt isn't worth committing to.
_MEANINGFUL_GAIN = 0.15


@dataclass
class PuntVerdict:
    """The simulated result of committing to one punt build."""

    categories: frozenset
    category_wins: float
    baseline_wins: float

    @property
    def gain(self) -> float:
        """Expected category wins gained versus not punting."""
        return self.category_wins - self.baseline_wins

    @property
    def is_recommended(self) -> bool:
        """Whether the punt clears the bar worth committing to."""
        return self.gain >= _MEANINGFUL_GAIN

    @property
    def label(self) -> str:
        """Human-readable build name."""
        if not self.categories:
            return "no punt"
        return "punt " + " + ".join(sorted(self.categories))

    def summary(self, display_names: Optional[Dict[str, str]] = None) -> str:
        """One line for the panel."""
        names = display_names or {}
        if not self.categories:
            return f"No punt: {self.category_wins:.1f} projected category wins"
        pretty = " + ".join(sorted(names.get(c, c) for c in self.categories))
        direction = "+" if self.gain >= 0 else ""
        return (
            f"Punt {pretty}: {self.category_wins:.1f} category wins "
            f"({direction}{self.gain:.2f})"
        )


def candidate_punts(board: Sequence[CategorySupply]) -> List[str]:
    """Categories worth testing as punts.

    A category is a candidate when you're already behind in it. Supply crunch
    breaks ties: being behind in a category that's drying up is a much stronger
    punt signal than being behind in one you can still fix.

    Args:
        board: The scarcity board.

    Returns:
        Category names, strongest punt signal first.
    """
    weak = [supply for supply in board if supply.deficit < _WEAKNESS_THRESHOLD]
    weak.sort(key=lambda s: (-s.crunch, s.deficit))
    return [supply.name for supply in weak]


def evaluate(
    state: DraftState,
    valued_available: Sequence[ValuedPlayer],
    valued_by_id: Dict[str, ValuedPlayer],
    board: Sequence[CategorySupply],
    max_builds: int = 12,
) -> List[PuntVerdict]:
    """Test candidate punt builds by simulation.

    Args:
        state: Normalized draft state.
        valued_available: Scored players still on the board.
        valued_by_id: Scored players by id.
        board: The scarcity board, used to pick candidates.
        max_builds: Cap on how many builds to simulate, so this stays fast
            enough to run on every pick.

    Returns:
        Verdicts sorted by expected category wins, best first. The no-punt
        baseline is always included so the panel can show the comparison.
    """
    baseline = simulate(state, valued_available, valued_by_id, punt=None)
    baseline_wins = baseline.category_wins(state.my_team_id)

    verdicts: List[PuntVerdict] = [
        PuntVerdict(
            categories=frozenset(),
            category_wins=baseline_wins,
            baseline_wins=baseline_wins,
        )
    ]

    candidates = candidate_punts(board)
    builds: List[Set[str]] = [{name} for name in candidates]
    for pair in itertools.combinations(candidates[:_PAIR_CANDIDATES], 2):
        builds.append(set(pair))

    for build in builds[: max(max_builds - 1, 0)]:
        standings = simulate(state, valued_available, valued_by_id, punt=build)
        verdicts.append(
            PuntVerdict(
                categories=frozenset(build),
                category_wins=standings.category_wins(state.my_team_id),
                baseline_wins=baseline_wins,
            )
        )

    verdicts.sort(key=lambda v: v.category_wins, reverse=True)
    return verdicts


def best_build(verdicts: Sequence[PuntVerdict]) -> PuntVerdict:
    """The build to actually play.

    Returns the highest-scoring punt only when it beats not punting by a
    meaningful margin; otherwise the no-punt build. Committing to a punt on a
    rounding error is how drafts get wrecked.
    """
    if not verdicts:
        return PuntVerdict(frozenset(), 0.0, 0.0)

    no_punt = next(
        (v for v in verdicts if not v.categories),
        PuntVerdict(frozenset(), verdicts[0].baseline_wins, verdicts[0].baseline_wins),
    )
    best = verdicts[0]
    return best if best.categories and best.is_recommended else no_punt
