"""How much of a roster actually starts.

A 13-man roster with 10 active slots means roughly a quarter of what you draft
sits on the bench on any given day — and *which* quarter depends on position
eligibility, not just on value. Draft five centers into a two-C league and the
third, fourth and fifth are worth a fraction of their raw z-score.

Ignoring this is how a valuation model talks you into a positionally broken team
that looks great on paper. This module applies the correction by running the
league's real slot layout through the existing
:func:`tools.matchup.roster_optimizer.optimize_roster_positions`.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from tools.draft.draft_state import DraftPlayer, RosterSlot
from tools.matchup.roster_optimizer import optimize_roster_positions

#: A benched player is not worthless — injuries, rest days and rotation mean he
#: still logs starts across a season — but he is worth much less than a player
#: who slots in every night. Tunable; the ordering of teams is not sensitive to
#: the exact figure, only to it being well below 1.0.
BENCH_WEIGHT = 0.35


def _eligibility(player: DraftPlayer) -> List[str]:
    """A player's slot eligibility, never empty.

    The draft store always supplies ``pos`` expanded to flex slots, but a missing
    or malformed value must not silently bench a player — that would quietly
    erase most of his value from every simulation. Falling back to Util keeps him
    playable while still respecting genuine positional scarcity.
    """
    return list(player.positions) if player.positions else ["Util"]


def slot_layout(roster_slots: Sequence[RosterSlot]) -> List[str]:
    """Expand roster slots into the flat position list the optimizer expects.

    ``[RosterSlot("C", 2), RosterSlot("Util", 2)]`` becomes
    ``["C", "C", "Util", "Util"]``.
    """
    layout: List[str] = []
    for slot in roster_slots:
        layout.extend([slot.position] * max(slot.count, 0))
    return layout


def startable_players(
    players: Sequence[DraftPlayer],
    roster_slots: Sequence[RosterSlot],
    ranks: Optional[Dict[str, int]] = None,
) -> set:
    """Which players would occupy an active slot on a full-health day.

    Args:
        players: The roster to assign.
        roster_slots: The league's slot layout, bench included.
        ranks: Optional player id -> rank, used to break ties between players of
            equal positional flexibility. Better players should win a contested
            slot, so pass your valuation ranking here.

    Returns:
        Set of player ids that land in an active slot.
    """
    layout = slot_layout(roster_slots)
    if not layout or not players:
        return set()

    # The optimizer benches anyone absent from players_with_games. On draft day
    # nobody has a schedule yet, so everyone is treated as playing and the
    # assignment turns purely on position eligibility and slot capacity.
    payload = [
        {"player_key": player.player_id, "eligible_positions": _eligibility(player)}
        for player in players
    ]
    all_ids = {player.player_id for player in players}

    assignments = optimize_roster_positions(
        players=payload,
        league_roster_positions=layout,
        players_with_games=all_ids,
        player_ranks=ranks or {},
    )

    inactive = {"BN", "IL", "IL+"}
    return {
        player_id
        for player_id, position in assignments.items()
        if position not in inactive
    }


def contribution_weights(
    players: Sequence[DraftPlayer],
    roster_slots: Sequence[RosterSlot],
    ranks: Optional[Dict[str, int]] = None,
) -> Dict[str, float]:
    """Per-player weight for how much of their production a team actually banks.

    Args:
        players: The roster to weigh.
        roster_slots: The league's slot layout.
        ranks: Optional tie-break ranking; better players win contested slots.

    Returns:
        Mapping of player id to weight — 1.0 for a starter, :data:`BENCH_WEIGHT`
        for a player squeezed out of the active lineup.
    """
    if not roster_slots:
        # No slot information means no basis to bench anyone.
        return {player.player_id: 1.0 for player in players}

    starters = startable_players(players, roster_slots, ranks)
    return {
        player.player_id: 1.0 if player.player_id in starters else BENCH_WEIGHT
        for player in players
    }


def positional_gaps(
    players: Sequence[DraftPlayer], roster_slots: Sequence[RosterSlot]
) -> Dict[str, int]:
    """Active slots this roster cannot currently fill.

    Tells the panel what you still *need*, as opposed to what is merely good.

    Args:
        players: The current roster.
        roster_slots: The league's slot layout.

    Returns:
        Mapping of position to how many of its active slots remain empty.
    """
    layout = [
        position
        for position in slot_layout(roster_slots)
        if position not in {"BN", "IL", "IL+"}
    ]
    if not layout:
        return {}

    payload = [
        {"player_key": player.player_id, "eligible_positions": _eligibility(player)}
        for player in players
    ]
    assignments = optimize_roster_positions(
        players=payload,
        league_roster_positions=layout,
        players_with_games={player.player_id for player in players},
        player_ranks={},
    )

    filled: Dict[str, int] = {}
    for position in assignments.values():
        if position not in {"BN", "IL", "IL+"}:
            filled[position] = filled.get(position, 0) + 1

    gaps: Dict[str, int] = {}
    for position in layout:
        gaps[position] = gaps.get(position, 0) + 1
    for position, count in filled.items():
        if position in gaps:
            gaps[position] -= count

    return {position: count for position, count in gaps.items() if count > 0}
