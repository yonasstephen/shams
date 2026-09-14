"""Compose valuation, scarcity, punt detection and simulation into a board.

The panel gets one headline pick, one reason, and three alternatives; everything
else sits behind a tab. That constraint drives this module: it does the full
analysis, then decides which single fact about the top pick is worth the two
seconds a manager has to read it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from tools.draft import (
    adp,
    projections,
    punt_detector,
    roster_fit,
    scarcity,
    schedule_value,
    simulator,
    value_model,
)
from tools.draft.draft_state import DraftPlayer, DraftState
from tools.draft.punt_detector import PuntVerdict
from tools.draft.scarcity import CategorySupply

#: How many candidates get the full standings simulation. Each one replays the
#: rest of the draft, so this is the compute knob.
_SIMULATED_CANDIDATES = 12
#: How deep the returned board goes.
_BOARD_DEPTH = 60
#: Alternatives shown next to the headline pick.
_ALTERNATIVES = 3
#: Below this survival probability, he will not be there at your next pick.
_AT_RISK = 0.35
#: How much one projected category win is worth in z-score units when ranking.
#: Forcing a pick reshuffles what everyone else gets, so the simulated delta is
#: noisy (±0.5 is common) while marginal value is stable. Weighting it at 1.0
#: lets standings impact break ties and promote genuinely better fits, without
#: letting simulation noise bury a clearly superior player.
_STANDINGS_WEIGHT = 1.0


@dataclass
class Recommendation:
    """One player, scored and explained."""

    player_id: str
    name: str
    positions: List[str]
    nba_team: str
    injury: str

    total_value: float
    marginal_value: float
    category_z: Dict[str, float] = field(default_factory=dict)

    standings_delta: Optional[float] = None
    survival: Optional[float] = None
    average_pick: Optional[float] = None
    value_gap: Optional[float] = None
    gap_label: str = ""
    reason: str = ""

    @property
    def score(self) -> float:
        """Ranking score: value above replacement, nudged by standings impact."""
        return self.marginal_value + _STANDINGS_WEIGHT * (self.standings_delta or 0.0)


@dataclass
class DraftBoard:
    """Everything the side panel renders."""

    headline: Optional[Recommendation] = None
    alternatives: List[Recommendation] = field(default_factory=list)
    board: List[Recommendation] = field(default_factory=list)

    supply: List[CategorySupply] = field(default_factory=list)
    heat_map: Dict[str, float] = field(default_factory=dict)

    punt: Optional[PuntVerdict] = None
    punt_options: List[PuntVerdict] = field(default_factory=list)

    my_roster: List[DraftPlayer] = field(default_factory=list)
    positional_gaps: Dict[str, int] = field(default_factory=dict)
    schedule_available: bool = False
    projection_source: str = ""
    projected_players: int = 0
    picks_until_my_turn: Optional[int] = None
    is_my_turn: bool = False
    seconds_remaining: Optional[int] = None
    current_pick: int = 0
    projected_category_wins: float = 0.0


def _build_reason(
    rec: Recommendation,
    supply_by_category: Dict[str, CategorySupply],
    punt: Set[str],
) -> str:
    """Pick the single most decision-relevant fact about this player.

    Ordered by what actually changes a pick: he won't last, he fixes the hole
    that's closing, he's a market steal, he moves the standings.
    """
    # 1. Urgency beats everything — you cannot wait on him.
    if rec.survival is not None and rec.survival < _AT_RISK:
        return f"Won't last to your next pick ({rec.survival:.0%} survival)"

    # 2. Fills a category you're losing where supply is drying up.
    best_fix: Optional[CategorySupply] = None
    for name, z in rec.category_z.items():
        if name in punt or z < scarcity.ELITE_Z:
            continue
        entry = supply_by_category.get(name)
        if entry is None or not entry.is_weakness:
            continue
        if best_fix is None or entry.deficit < best_fix.deficit:
            best_fix = entry
    if best_fix is not None:
        if best_fix.is_supply_crunch:
            return (
                f"Fills your worst category ({best_fix.display_name}) — only "
                f"{best_fix.elite_remaining} elite left, {best_fix.elite_surviving:.1f} "
                f"survive to your next pick"
            )
        return f"Fills your worst category ({best_fix.display_name})"

    # 3. The market is letting him fall.
    if rec.value_gap is not None and rec.value_gap >= 8:
        return f"{rec.gap_label.capitalize()}: ADP {rec.average_pick:.0f}, still here"

    # 4. Otherwise, what he does to your finish.
    if rec.standings_delta:
        return f"{rec.standings_delta:+.2f} projected category wins"

    return "Best available on your board"


def _to_recommendation(
    valued: value_model.ValuedPlayer,
    marginal: float,
    punt: Set[str],
) -> Recommendation:
    """Convert a scored player into a panel row."""
    player: DraftPlayer = valued.player
    return Recommendation(
        player_id=player.player_id,
        name=player.name,
        positions=list(player.positions),
        nba_team=player.nba_team,
        injury=player.injury,
        total_value=valued.total(punt),
        marginal_value=marginal,
        category_z=dict(valued.category_z),
        average_pick=adp.player_adp(player),
    )


def recommend(
    state: DraftState,
    pool_size: Optional[int] = None,
    source: Optional[projections.ProjectionSource] = None,
) -> DraftBoard:
    """Analyze the draft and produce the panel's board.

    Args:
        state: Normalized draft state from the extension.
        pool_size: Reference pool size for valuation. Defaults to the number of
            players the league will actually draft.
        source: Where projections come from. Defaults to our exported CSV when
            one exists for the season, otherwise Yahoo's own numbers.

    Returns:
        The full :class:`DraftBoard`.
    """
    board = DraftBoard(
        picks_until_my_turn=state.picks_until_my_turn(),
        is_my_turn=state.is_my_turn(),
        seconds_remaining=state.seconds_remaining,
        current_pick=state.current_pick,
        my_roster=state.my_roster(),
    )

    if not state.players or not state.categories:
        return board

    # Swap in projections before anything is valued, so scarcity, punts and the
    # simulator all see the same numbers.
    if source is None:
        source = projections.load_source(state.season)
    board.projected_players = projections.apply_source(state.players, source)
    board.projection_source = source.name

    if pool_size is None:
        pool_size = max(state.num_teams * state.roster_size, 1)

    context = value_model.build_context(state.players.values(), state.categories, pool_size)
    valued_all = value_model.value_players(state.players.values(), context)
    valued_by_id = {v.player_id: v for v in valued_all}

    available = [
        valued_by_id[p.player_id]
        for p in state.available_players()
        if p.player_id in valued_by_id
    ]
    if not available:
        return board

    # Scarcity first — the punt decision depends on it.
    board.supply = scarcity.analyze(state, available, valued_by_id)
    board.heat_map = scarcity.heat_map(board.supply)
    supply_by_category = {s.name: s for s in board.supply}

    # Schedule is optional: without a cached season the assistant runs
    # schedule-neutral and says so, rather than pretending every team is average.
    board.schedule_available = bool(state.season) and schedule_value.is_available(state.season)
    schedule_adjustments = None
    if board.schedule_available:
        schedules = schedule_value.league_schedules(
            [p.player.nba_team for p in available], state.season
        )
        schedule_adjustments = schedule_value.adjustments(schedules)

    board.punt_options = punt_detector.evaluate(state, available, valued_by_id, board.supply)
    board.punt = punt_detector.best_build(board.punt_options)
    punt: Set[str] = set(board.punt.categories) if board.punt else set()
    board.projected_category_wins = board.punt.category_wins if board.punt else 0.0

    # Rank under the chosen build, then price against replacement at your turn.
    ranked = value_model.rank_by_value(available, punt)
    picks_until = state.picks_until_my_turn()
    replacement = value_model.replacement_value(
        available, index=picks_until if picks_until is not None else len(available) // 2, punt=punt
    )
    marginals = value_model.marginal_values(available, replacement, punt)

    rows = [
        _to_recommendation(valued, marginals.get(valued.player_id, 0.0), punt)
        for valued in ranked[:_BOARD_DEPTH]
    ]

    # ADP context for the whole board.
    gaps = adp.value_gaps([row.player_id for row in rows], state.players)
    for row, gap in zip(rows, gaps):
        row.value_gap = gap.gap
        row.gap_label = gap.label

    # Survival at your next pick.
    if picks_until:
        target = state.current_pick + picks_until
        for row in rows:
            player = state.players.get(row.player_id)
            if player is not None:
                row.survival = adp.survival_probability(player, target)
    elif state.is_my_turn():
        for row in rows:
            row.survival = None

    # The expensive step, limited to the shortlist.
    shortlist = [row.player_id for row in rows[:_SIMULATED_CANDIDATES]]
    impacts = {
        impact.player_id: impact
        for impact in simulator.impact_of(
            state,
            available,
            valued_by_id,
            shortlist,
            punt=punt,
            schedule_adjustments=schedule_adjustments,
        )
    }
    for row in rows:
        impact = impacts.get(row.player_id)
        if impact is not None:
            row.standings_delta = impact.delta

    # Re-order the shortlist by value above replacement adjusted for what each
    # pick does to your projected finish.
    head = sorted(rows[:_SIMULATED_CANDIDATES], key=lambda r: r.score, reverse=True)
    rows = head + rows[_SIMULATED_CANDIDATES:]

    for row in rows:
        row.reason = _build_reason(row, supply_by_category, punt)

    board.positional_gaps = roster_fit.positional_gaps(
        state.my_roster(), state.roster_slots
    )
    board.board = rows
    board.headline = rows[0]
    board.alternatives = rows[1 : 1 + _ALTERNATIVES]
    return board


def summarize(board: DraftBoard) -> List[str]:
    """A few lines describing the board, for CLI output and debugging."""
    lines: List[str] = []
    if board.headline:
        lines.append(f"PICK: {board.headline.name} — {board.headline.reason}")
    for alt in board.alternatives:
        lines.append(f"  alt: {alt.name} ({alt.marginal_value:+.2f})")
    if board.punt:
        lines.append(f"BUILD: {board.punt.label} ({board.projected_category_wins:.1f} cat wins)")
    for supply in board.supply[:3]:
        lines.append(f"  {supply.summary()}")
    return lines
