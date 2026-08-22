"""Average draft position and survival probability.

Yahoo's draft store ships ADP directly on every player (``average-pick``, with
``preseason-average-pick`` as a fallback before in-season data accumulates), so
no external ADP source is needed.

The question that actually decides picks is not "what is his ADP" but "will he
still be there at my next pick?" Because ``draftOrder.order`` publishes every
pick of the draft up front, the gap to your next turn is exact rather than
estimated, and survival collapses to a probability over ADP.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

from tools.draft.draft_state import DraftPlayer

# Spread of actual draft position around ADP, in picks. Drafts are noisier than
# ADP suggests early (managers reach for their guys) and tighter late, but a
# single sigma proportional to ADP models the shape well enough to rank on.
_BASE_SIGMA = 6.0
_SIGMA_GROWTH = 0.18


def player_adp(player: DraftPlayer) -> Optional[float]:
    """Best available ADP for a player.

    Prefers live ADP, falls back to preseason. Returns None when Yahoo has no
    market data, which happens for deep bench players nobody drafts.
    """
    for value in (player.average_pick, player.preseason_average_pick):
        if value is not None and value > 0:
            return value
    return None


def adp_sigma(adp: float) -> float:
    """Standard deviation of actual pick around ADP, widening later in the draft."""
    return _BASE_SIGMA + _SIGMA_GROWTH * adp


def _normal_cdf(x: float) -> float:
    """Standard normal CDF."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def survival_probability(player: DraftPlayer, target_pick: int) -> float:
    """Probability the player is still available at ``target_pick``.

    Modelled as P(actual draft position >= target_pick) with actual position
    normally distributed around ADP.

    Args:
        player: The player in question.
        target_pick: Overall pick number (0-based) you want him at.

    Returns:
        Probability in [0, 1]. Players with no ADP are treated as very likely to
        last, since nobody is drafting them.
    """
    adp = player_adp(player)
    if adp is None:
        return 1.0
    if target_pick <= 0:
        return 1.0

    sigma = adp_sigma(adp)
    return 1.0 - _normal_cdf((target_pick - adp) / sigma)


@dataclass
class ValueGap:
    """How a player's market price compares to where you'd take him."""

    player_id: str
    adp: Optional[float]
    your_rank: int
    #: Positive means the market is letting him fall past your valuation.
    gap: Optional[float]

    @property
    def label(self) -> str:
        """Human-readable verdict."""
        if self.gap is None:
            return "unranked"
        if self.gap >= 12:
            return "steal"
        if self.gap >= 5:
            return "value"
        if self.gap <= -12:
            return "big reach"
        if self.gap <= -5:
            return "reach"
        return "market price"


def value_gaps(ranked_player_ids: List[str], players: Dict[str, DraftPlayer]) -> List[ValueGap]:
    """Compare your ranking against ADP.

    Args:
        ranked_player_ids: Available players in *your* order, best first.
        players: Player lookup.

    Returns:
        One :class:`ValueGap` per ranked player, same order.
    """
    gaps: List[ValueGap] = []
    for index, player_id in enumerate(ranked_player_ids):
        player = players.get(player_id)
        adp = player_adp(player) if player else None
        your_rank = index + 1
        gaps.append(
            ValueGap(
                player_id=player_id,
                adp=adp,
                your_rank=your_rank,
                gap=None if adp is None else adp - your_rank,
            )
        )
    return gaps


def expected_survivors(
    candidates: Iterable[DraftPlayer], target_pick: int
) -> float:
    """Expected number of the given players still available at ``target_pick``.

    Summing survival probabilities gives the expectation directly, which is what
    the scarcity board needs: "how many of the remaining elite assist sources
    will still be there when I pick again?"
    """
    return sum(survival_probability(player, target_pick) for player in candidates)
