"""Finish the draft in simulation, then score the resulting standings.

This is what turns "who is the best player" into "which pick wins me the most
categories". It plays out every remaining pick — yours with your valuation,
everyone else's along ADP, which is what managers actually follow — and then
compares the finished rosters category by category.

**Why summed z-scores stand in for real category totals.** For a counting
category ``z = (x - mean) / sd``, so a team's weighted total is
``(sum(w*x) - mean * sum(w)) / sd``. Teams that fill the same number of active
slots carry the same ``sum(w)``, and in a snake draft with a workable roster that
is nearly all of them — so the ordering is the ordering by weighted production.
A team that *cannot* fill its slots carries a smaller ``sum(w)`` and so loses a
little less to the ``mean`` term; that artifact is second-order next to the
production it forfeits by benching players, which is the effect being modelled.
For percentage categories the scored quantity is already "makes above baseline",
which is additive and moves with the team's true percentage.

``tools/matchup/matchup_projection.py`` is deliberately untouched: it needs live
Yahoo roster state keyed by date, none of which exists on draft day.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set

from tools.draft import adp, roster_fit
from tools.draft.draft_state import DraftState
from tools.draft.value_model import ValuedPlayer


@dataclass
class SimulatedStandings:
    """Projected end-of-draft category totals for every team."""

    #: team id -> category name -> summed z
    totals: Dict[str, Dict[str, float]] = field(default_factory=dict)
    #: team id -> players added during the simulation
    additions: Dict[str, List[str]] = field(default_factory=dict)

    def category_wins(self, team_id: str) -> float:
        """Expected categories won against an average opponent.

        Scored as the fraction of opponents beaten in each category, summed over
        categories. With 14 teams, beating 13 of 13 in a category scores 1.0.
        """
        mine = self.totals.get(team_id)
        if not mine:
            return 0.0

        opponents = [tid for tid in self.totals if tid != team_id]
        if not opponents:
            return 0.0

        wins = 0.0
        for category, value in mine.items():
            beaten = sum(
                1 for tid in opponents if value > self.totals[tid].get(category, 0.0)
            )
            wins += beaten / len(opponents)
        return wins


def _opponent_order(valued_available: Sequence[ValuedPlayer]) -> List[ValuedPlayer]:
    """Rank the pool the way the rest of the league drafts: by ADP.

    Players without ADP fall to the back — nobody is taking them early.
    """

    def sort_key(valued: ValuedPlayer):
        value = adp.player_adp(valued.player)
        return (value is None, value if value is not None else 0.0)

    return sorted(valued_available, key=sort_key)


def _my_order(
    valued_available: Sequence[ValuedPlayer], punt: Optional[Set[str]]
) -> List[ValuedPlayer]:
    """Rank the pool by your punt-aware valuation."""
    return sorted(valued_available, key=lambda v: v.total(punt), reverse=True)


def simulate(
    state: DraftState,
    valued_available: Sequence[ValuedPlayer],
    valued_by_id: Dict[str, ValuedPlayer],
    punt: Optional[Set[str]] = None,
    forced_pick: Optional[str] = None,
    schedule_adjustments: Optional[Dict[str, float]] = None,
) -> SimulatedStandings:
    """Play out the rest of the draft and return projected standings.

    Rosters are assembled first, then scored, so each team's totals can be
    weighted by who would actually start. A positionally lopsided roster — five
    centres in a two-C league — banks much less than the sum of its z-scores.

    Args:
        state: Normalized draft state.
        valued_available: Scored players still on the board.
        valued_by_id: Scored players by id, including already-drafted ones.
        punt: Categories you are punting; shapes only *your* picks.
        forced_pick: A player id you take with your next pick, used to measure
            what a specific choice does to your finish.
        schedule_adjustments: Optional team-abbreviation multipliers from
            :mod:`tools.draft.schedule_value`. Omitted means schedule-neutral.

    Returns:
        Projected end-of-draft standings.
    """
    standings = SimulatedStandings()
    category_names = [category.name for category in state.categories]

    # Seed each roster with the picks already made.
    rosters: Dict[str, List[str]] = {team_id: [] for team_id in state.teams}
    for pick in state.picks:
        if pick.player_id in valued_by_id:
            rosters.setdefault(pick.team_id, []).append(pick.player_id)
    for team_id in rosters:
        standings.additions[team_id] = []

    taken: Set[str] = set()
    my_queue = _my_order(valued_available, punt)
    opponent_queue = _opponent_order(valued_available)
    my_cursor = 0
    opponent_cursor = 0

    def award(team_id: str, valued: ValuedPlayer) -> None:
        taken.add(valued.player_id)
        rosters.setdefault(team_id, []).append(valued.player_id)
        standings.additions.setdefault(team_id, []).append(valued.player_id)

    if forced_pick and forced_pick not in taken:
        forced = valued_by_id.get(forced_pick)
        if forced is not None:
            award(state.my_team_id, forced)

    for index in range(state.current_pick, len(state.pick_order)):
        team_id = state.pick_order[index]
        if not team_id:
            continue

        # The forced pick already consumed this team's turn.
        if forced_pick and team_id == state.my_team_id and index == state.current_pick:
            continue

        if team_id == state.my_team_id:
            while my_cursor < len(my_queue) and my_queue[my_cursor].player_id in taken:
                my_cursor += 1
            if my_cursor >= len(my_queue):
                continue
            award(team_id, my_queue[my_cursor])
        else:
            while (
                opponent_cursor < len(opponent_queue)
                and opponent_queue[opponent_cursor].player_id in taken
            ):
                opponent_cursor += 1
            if opponent_cursor >= len(opponent_queue):
                continue
            award(team_id, opponent_queue[opponent_cursor])

    # Score the finished rosters, weighting each player by whether he would
    # actually occupy an active slot.
    ranks = {
        valued.player_id: index
        for index, valued in enumerate(_my_order(list(valued_by_id.values()), punt))
    }
    for team_id, player_ids in rosters.items():
        players = [
            valued_by_id[pid].player for pid in player_ids if pid in valued_by_id
        ]
        weights = roster_fit.contribution_weights(players, state.roster_slots, ranks)

        totals = {name: 0.0 for name in category_names}
        for player_id in player_ids:
            valued = valued_by_id.get(player_id)
            if valued is None:
                continue
            weight = weights.get(player_id, 1.0)
            if schedule_adjustments:
                weight *= schedule_adjustments.get(valued.player.nba_team, 1.0)
            for name in category_names:
                totals[name] += valued.category_z.get(name, 0.0) * weight
        standings.totals[team_id] = totals

    return standings


@dataclass
class StandingsImpact:
    """What taking a specific player does to your projected finish."""

    player_id: str
    category_wins: float
    baseline_wins: float

    @property
    def delta(self) -> float:
        """Change in expected category wins versus your default pick."""
        return self.category_wins - self.baseline_wins


def baseline_wins(
    state: DraftState,
    valued_available: Sequence[ValuedPlayer],
    valued_by_id: Dict[str, ValuedPlayer],
    punt: Optional[Set[str]] = None,
    schedule_adjustments: Optional[Dict[str, float]] = None,
) -> float:
    """Expected category wins if you simply take your top-ranked player."""
    standings = simulate(
        state,
        valued_available,
        valued_by_id,
        punt=punt,
        schedule_adjustments=schedule_adjustments,
    )
    return standings.category_wins(state.my_team_id)


def impact_of(
    state: DraftState,
    valued_available: Sequence[ValuedPlayer],
    valued_by_id: Dict[str, ValuedPlayer],
    candidates: Sequence[str],
    punt: Optional[Set[str]] = None,
    schedule_adjustments: Optional[Dict[str, float]] = None,
) -> List[StandingsImpact]:
    """Measure each candidate pick against the default pick.

    Args:
        state: Normalized draft state.
        valued_available: Scored players still on the board.
        valued_by_id: Scored players by id.
        candidates: Player ids to evaluate — keep this to the shortlist, since
            each one replays the remaining draft.
        punt: Categories you are punting.
        schedule_adjustments: Optional team-abbreviation multipliers.

    Returns:
        One :class:`StandingsImpact` per candidate, best delta first.
    """
    base = baseline_wins(
        state, valued_available, valued_by_id, punt=punt,
        schedule_adjustments=schedule_adjustments,
    )

    impacts: List[StandingsImpact] = []
    for player_id in candidates:
        standings = simulate(
            state,
            valued_available,
            valued_by_id,
            punt=punt,
            forced_pick=player_id,
            schedule_adjustments=schedule_adjustments,
        )
        impacts.append(
            StandingsImpact(
                player_id=player_id,
                category_wins=standings.category_wins(state.my_team_id),
                baseline_wins=base,
            )
        )

    impacts.sort(key=lambda i: i.delta, reverse=True)
    return impacts
