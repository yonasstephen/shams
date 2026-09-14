"""Common shape for an external projection source."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Protocol

#: Suffixes that differ between sources for the same player.
_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}

#: Per-game stats an external source is expected to supply. Percentage
#: categories are absent on purpose: a source that gives only FG% without
#: attempts cannot be blended correctly, so attempts are what we ask for.
EXTERNAL_STATS = (
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


def normalize_name(name: str) -> str:
    """Fold a player name so two sources spelling it differently still match.

    Handles the three things that actually differ in practice: diacritics
    (Jokić/Jokic), punctuation (O'Neale/ONeale, Gilgeous-Alexander), and
    generational suffixes (Jaren Jackson Jr./Jaren Jackson).
    """
    ascii_name = (
        unicodedata.normalize("NFKD", name or "")
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    cleaned = ascii_name.lower().replace(".", "").replace("'", "").replace("-", " ")
    parts = [part for part in cleaned.split() if part not in _SUFFIXES]
    return " ".join(parts)


@dataclass
class ExternalProjection:
    """One player's projected line from one source."""

    name: str
    source: str
    games: Optional[float] = None
    minutes_per_game: Optional[float] = None
    #: Per-game stats, in :data:`EXTERNAL_STATS` terms.
    per_game: Dict[str, float] = field(default_factory=dict)
    team: str = ""
    positions: str = ""

    @property
    def key(self) -> str:
        """Normalized name, used to join sources together."""
        return normalize_name(self.name)

    @property
    def is_usable(self) -> bool:
        """Whether there is enough here to blend.

        A line with no games or no production is a placeholder row, which these
        exports are full of for two-way and inactive players.
        """
        if not self.games or self.games <= 0:
            return False
        return any(value for value in self.per_game.values())


class Source(Protocol):
    """Supplies projections for a season."""

    name: str

    def load(self) -> List[ExternalProjection]:
        """Return every projection this source knows about."""
