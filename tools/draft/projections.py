"""Where the draft assistant's player projections come from.

Two sources, one interface:

- :class:`YahooStoreSource` uses the ``projected_stats`` already present in the
  draft room. It needs nothing external, which is why it is the default.
- :class:`CsvSource` uses our own model's export, with hand overrides applied.

Keeping them behind a protocol is what lets the projection model be developed,
backtested and swapped in later without touching valuation, scarcity, punt
detection or the simulator. It is also what lets a bad projection file be
abandoned mid-draft by deleting it.

The CSV carries **per-game** lines; Yahoo carries **season totals**. Converting
CSV rows to totals here means everything downstream sees one shape.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Protocol

from tools.draft.draft_state import DraftPlayer
from tools.draft.stat_ids import RATIO_STATS

logger = logging.getLogger(__name__)

#: Stats carried per-game in the CSV and converted to totals for the engine.
_COUNTING = (
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


class ProjectionSource(Protocol):
    """Supplies a projected season line for a player."""

    name: str

    def line_for(self, player: DraftPlayer) -> Optional[Dict[str, float]]:
        """Projected season totals for a player, or None if unknown."""


class YahooStoreSource:
    """Yahoo's own projections, as shipped in the draft room.

    Already parsed onto :attr:`DraftPlayer.projected`, so this is a pass-through
    that exists to make the default explicit rather than implicit.
    """

    name = "yahoo"

    def line_for(self, player: DraftPlayer) -> Optional[Dict[str, float]]:
        """Return Yahoo's projected totals, or None when the line is empty."""
        return dict(player.projected) if player.has_projection else None


class CsvSource:
    """Our model's projections, loaded from the exported CSV.

    Indexed by both Yahoo id and normalized name: the CSV is keyed on NBA ids,
    and only players the model has seen carry a Yahoo id, so names are the
    fallback for anyone added by hand in the overrides file.
    """

    name = "shams-csv"

    def __init__(self, rows: List[Dict[str, object]]):
        self._by_yahoo_id: Dict[str, Dict[str, object]] = {}
        self._by_name: Dict[str, Dict[str, object]] = {}

        for row in rows:
            yahoo_id = str(row.get("yahoo_id") or "").strip()
            if yahoo_id:
                self._by_yahoo_id[yahoo_id] = row
            name = _normalize(str(row.get("name") or ""))
            if name:
                self._by_name[name] = row

    def __len__(self) -> int:
        return len(self._by_name)

    def line_for(self, player: DraftPlayer) -> Optional[Dict[str, float]]:
        """Projected totals for a player, converted from the CSV's per-game."""
        row = self._by_yahoo_id.get(player.player_id) or self._by_name.get(
            _normalize(player.name)
        )
        if row is None:
            return None

        games = row.get("gp")
        try:
            games = float(games)
        except (TypeError, ValueError):
            return None
        if games <= 0:
            return None

        totals: Dict[str, float] = {"games_played": games}
        for stat in _COUNTING:
            try:
                totals[stat] = float(row.get(stat) or 0.0) * games
            except (TypeError, ValueError):
                totals[stat] = 0.0

        # Rebuild ratios from the totals rather than trusting the CSV's column,
        # which may be stale if volume was overridden by hand.
        for ratio, (makes, attempts) in RATIO_STATS.items():
            denominator = totals.get(attempts, 0.0)
            totals[ratio] = totals.get(makes, 0.0) / denominator if denominator else 0.0

        return totals


def _normalize(name: str) -> str:
    """Fold a name for matching: ASCII, lowercase, no punctuation or suffixes."""
    import unicodedata

    ascii_name = (
        unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    )
    cleaned = ascii_name.lower().replace(".", "").replace("'", "").replace("-", " ")
    parts = [part for part in cleaned.split() if part not in {"jr", "sr", "ii", "iii", "iv"}]
    return " ".join(parts)


def load_source(season: str, prefer_csv: bool = True) -> ProjectionSource:
    """Pick the projection source for a draft.

    Args:
        season: Season being drafted, e.g. ``2026-27``.
        prefer_csv: Use our model's export when one exists.

    Returns:
        The chosen source. Falls back to Yahoo whenever the CSV is missing or
        unreadable — a draft should never fail because a projection file is
        absent.
    """
    if prefer_csv and season:
        try:
            from tools.projections.export import load_projections

            rows = load_projections(season)
            if rows:
                logger.info("Using %d projections from CSV for %s", len(rows), season)
                return CsvSource(rows)
        except (OSError, ImportError) as exc:
            logger.warning("Could not load projection CSV: %s", exc)

    return YahooStoreSource()


#: Yahoo's injury code for a player who is not on an NBA roster at all.
_NOT_ACTIVE = "NA"


def _is_inactive(player: DraftPlayer) -> bool:
    """Whether Yahoo says this player is not in the league.

    A history-based model happily projects a retired player — it has three
    seasons of his box scores and no way to know he stopped playing. Yahoo does
    know, and marks him ``inj: "NA"`` with an all-zero line. Trusting that flag
    is what stops our CSV from putting last year's retirees back on the board.
    """
    return player.injury == _NOT_ACTIVE and not player.has_projection


def apply_source(players: Dict[str, DraftPlayer], source: ProjectionSource) -> int:
    """Overwrite each player's projected line from ``source``.

    Players the source does not know keep whatever they already had, so a
    partial CSV degrades to a Yahoo/CSV blend rather than blanking the pool.
    Players Yahoo flags as not active are left alone regardless of what the
    source says about them.

    Args:
        players: The draft pool, by player id.
        source: Where the projections come from.

    Returns:
        How many players the source supplied.
    """
    if isinstance(source, YahooStoreSource):
        return sum(1 for player in players.values() if player.has_projection)

    applied = 0
    for player in players.values():
        if _is_inactive(player):
            continue
        line = source.line_for(player)
        if line:
            player.projected = line
            applied += 1
    return applied
