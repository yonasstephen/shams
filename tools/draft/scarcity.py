"""Category supply, demand, and tier runway.

This answers the question every drafter asks and no tool on Yahoo answers: *the
first two rounds went centers — are there still enough assist guys left, or
should I punt?*

Three views, computed from one pass:

- **Supply** — how many real contributors in a category remain on the board.
- **Demand** — how many teams still need one, given what they've drafted.
- **Runway** — how many of them survive to your next pick, and where the next
  tier cliff falls.

The punt verdict in :mod:`tools.draft.punt_detector` is built on top of these.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from tools.draft import adp
from tools.draft.draft_state import DraftState
from tools.draft.value_model import ValuedPlayer

#: A player at or above this category z is a genuine difference-maker there.
ELITE_Z = 1.0
#: At or above this, he at least does not hurt you.
STARTER_Z = 0.0
#: How deep to look when hunting for the next tier cliff.
_CLIFF_DEPTH = 15


@dataclass
class CategorySupply:
    """Supply, demand and runway for one scoring category."""

    name: str
    display_name: str

    # Where you stand
    my_total: float = 0.0
    my_rank: int = 0
    league_mean: float = 0.0
    league_teams: int = 0

    # What's left on the board
    elite_remaining: int = 0
    starter_remaining: int = 0
    best_available: float = 0.0

    # Who else wants it
    teams_below_mean: int = 0

    # Runway
    picks_until_my_turn: Optional[int] = None
    elite_surviving: float = 0.0
    cliff_in_picks: Optional[int] = None
    cliff_drop: float = 0.0

    @property
    def crunch(self) -> float:
        """Demand over supply. Above 1.0 means more needy teams than elite sources."""
        return self.teams_below_mean / self.elite_remaining if self.elite_remaining else float(
            self.teams_below_mean
        )

    @property
    def is_supply_crunch(self) -> bool:
        """Whether the category is drying up faster than teams can fill it."""
        return self.crunch >= 1.0 and self.elite_remaining <= self.league_teams

    @property
    def deficit(self) -> float:
        """How far below the average team you are in this category."""
        return self.my_total - self.league_mean

    @property
    def is_weakness(self) -> bool:
        """Whether you are meaningfully behind the field here."""
        return self.deficit < 0

    def summary(self) -> str:
        """One line for the panel."""
        if self.elite_remaining == 0:
            supply = "no elite sources left"
        else:
            supply = f"{self.elite_remaining} elite left"
        survivors = f"{self.elite_surviving:.1f} survive to your pick"
        return f"{self.display_name}: {supply}, {survivors}, {self.teams_below_mean} teams needy"


def _team_totals(
    state: DraftState, valued_by_id: Dict[str, ValuedPlayer], category: str
) -> Dict[str, float]:
    """Summed category z for every team's current roster."""
    totals: Dict[str, float] = {team_id: 0.0 for team_id in state.teams}
    for pick in state.picks:
        valued = valued_by_id.get(pick.player_id)
        if valued is None:
            continue
        totals.setdefault(pick.team_id, 0.0)
        totals[pick.team_id] += valued.category_z.get(category, 0.0)
    return totals


def _find_cliff(sorted_z: Sequence[float]) -> tuple:
    """Locate the biggest quality drop among the top available in a category.

    Args:
        sorted_z: Category z of available players, best first.

    Returns:
        Tuple of (picks until the cliff, size of the drop). ``(None, 0.0)`` when
        there is no meaningful cliff.
    """
    window = list(sorted_z[:_CLIFF_DEPTH])
    if len(window) < 2:
        return None, 0.0

    best_index, best_drop = None, 0.0
    for index in range(len(window) - 1):
        drop = window[index] - window[index + 1]
        if drop > best_drop:
            best_index, best_drop = index + 1, drop
    return best_index, best_drop


def analyze(
    state: DraftState,
    valued_available: Sequence[ValuedPlayer],
    valued_by_id: Dict[str, ValuedPlayer],
) -> List[CategorySupply]:
    """Build the scarcity board.

    Args:
        state: The normalized draft state.
        valued_available: Scored players still on the board.
        valued_by_id: Scored players by id, including drafted ones, so team
            rosters can be totalled.

    Returns:
        One :class:`CategorySupply` per scoring category, most urgent first.
    """
    picks_until = state.picks_until_my_turn()
    my_next_pick = state.current_pick + picks_until if picks_until is not None else None

    board: List[CategorySupply] = []
    for category in state.categories:
        name = category.name
        supply = CategorySupply(
            name=name,
            display_name=category.display_name,
            league_teams=len(state.teams) or state.num_teams,
            picks_until_my_turn=picks_until,
        )

        # --- where you stand -------------------------------------------
        totals = _team_totals(state, valued_by_id, name)
        if totals:
            supply.my_total = totals.get(state.my_team_id, 0.0)
            supply.league_mean = statistics.fmean(totals.values())
            ordered = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
            supply.my_rank = next(
                (i + 1 for i, (tid, _) in enumerate(ordered) if tid == state.my_team_id), 0
            )
            supply.teams_below_mean = sum(1 for v in totals.values() if v < supply.league_mean)

        # --- what's left -----------------------------------------------
        category_z = sorted(
            (v.category_z.get(name, 0.0) for v in valued_available), reverse=True
        )
        supply.elite_remaining = sum(1 for z in category_z if z >= ELITE_Z)
        supply.starter_remaining = sum(1 for z in category_z if z >= STARTER_Z)
        supply.best_available = category_z[0] if category_z else 0.0

        # --- runway ------------------------------------------------------
        if my_next_pick is not None:
            elites = [
                v.player for v in valued_available if v.category_z.get(name, 0.0) >= ELITE_Z
            ]
            supply.elite_surviving = adp.expected_survivors(elites, my_next_pick)

        supply.cliff_in_picks, supply.cliff_drop = _find_cliff(category_z)
        board.append(supply)

    # Most urgent first: a category you're behind in, with supply drying up.
    board.sort(key=lambda s: (s.deficit >= 0, -s.crunch, s.deficit))
    return board


def heat_map(board: Sequence[CategorySupply]) -> Dict[str, float]:
    """Your standing per category relative to the average team.

    Positive means ahead of the field, negative behind. This is the number the
    panel's category heat map renders.
    """
    return {supply.name: supply.deficit for supply in board}
