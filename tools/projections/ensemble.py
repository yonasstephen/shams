"""Blend external projections and reconcile them with our own model.

Two jobs, as the plan set out:

1. **Benchmark.** Compare our model against the consensus and surface where they
   disagree sharply. A large disagreement is not proof our model is wrong, but
   it is the shortlist worth a human look before draft day.
2. **Fill the blind spot.** Rookies and role-changers have no usable history, so
   the model cannot see them at all. The consensus can, and those players get
   taken from it.

The blend is a **median**, not a mean. Projection sources disagree most about
exactly the players they are least sure of, and one wild outlier on a rookie
would drag a mean badly. The median simply ignores it.
"""

from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from tools.projections.export import STAT_COLUMNS
from tools.projections.marcel import ProjectedLine
from tools.projections.sources.base import (
    EXTERNAL_STATS,
    ExternalProjection,
    Source,
    normalize_name,
)

logger = logging.getLogger(__name__)

#: Relative gap in projected points before a player is flagged for review.
DISAGREEMENT_THRESHOLD = 0.30
#: A consensus line needs at least this many sources to stand on its own.
MIN_SOURCES_FOR_ROOKIE = 1


@dataclass
class Consensus:
    """Median line across sources for one player."""

    key: str
    name: str
    sources: List[str] = field(default_factory=list)
    games: Optional[float] = None
    minutes_per_game: Optional[float] = None
    per_game: Dict[str, float] = field(default_factory=dict)
    team: str = ""
    positions: str = ""

    @property
    def source_count(self) -> int:
        """How many sources contributed."""
        return len(self.sources)


@dataclass
class Disagreement:
    """Where our model and the consensus part ways."""

    name: str
    stat: str
    ours: float
    consensus: float
    sources: int

    @property
    def relative_gap(self) -> float:
        """Gap as a fraction of the larger value."""
        largest = max(abs(self.ours), abs(self.consensus))
        return abs(self.ours - self.consensus) / largest if largest else 0.0


def _median(values: Sequence[float]) -> Optional[float]:
    """Median of the values present, or None when there are none."""
    present = [value for value in values if value is not None]
    return statistics.median(present) if present else None


def build_consensus(sources: Sequence[Source]) -> Dict[str, Consensus]:
    """Combine sources into one median line per player.

    Args:
        sources: Loaded projection sources.

    Returns:
        Normalized name -> consensus line.
    """
    collected: Dict[str, List[ExternalProjection]] = {}
    for source in sources:
        try:
            entries = source.load()
        except Exception as exc:  # pylint: disable=broad-except
            # One bad source must not take the ensemble down.
            logger.warning("Source %s failed to load: %s", source.name, exc)
            continue
        for entry in entries:
            collected.setdefault(entry.key, []).append(entry)

    consensus: Dict[str, Consensus] = {}
    for key, entries in collected.items():
        merged = Consensus(
            key=key,
            name=entries[0].name,
            sources=[entry.source for entry in entries],
            team=next((e.team for e in entries if e.team), ""),
            positions=next((e.positions for e in entries if e.positions), ""),
        )
        merged.games = _median([entry.games for entry in entries])
        merged.minutes_per_game = _median(
            [entry.minutes_per_game for entry in entries]
        )
        for stat in EXTERNAL_STATS:
            value = _median([entry.per_game.get(stat) for entry in entries])
            if value is not None:
                merged.per_game[stat] = value
        consensus[key] = merged

    return consensus


def find_disagreements(
    projections: Dict[int, ProjectedLine],
    consensus: Dict[str, Consensus],
    stat: str = "points",
    threshold: float = DISAGREEMENT_THRESHOLD,
) -> List[Disagreement]:
    """Players where our model and the consensus differ sharply.

    Args:
        projections: Our model's output.
        consensus: The blended external lines.
        stat: Which stat to compare on.
        threshold: Relative gap at which to flag.

    Returns:
        Disagreements, largest gap first.
    """
    flagged: List[Disagreement] = []
    for line in projections.values():
        entry = consensus.get(normalize_name(line.name))
        if entry is None or stat not in entry.per_game:
            continue
        item = Disagreement(
            name=line.name,
            stat=stat,
            ours=line.per_game.get(stat, 0.0),
            consensus=entry.per_game[stat],
            sources=entry.source_count,
        )
        if item.relative_gap >= threshold:
            flagged.append(item)

    flagged.sort(key=lambda d: d.relative_gap, reverse=True)
    return flagged


def missing_from_model(
    projections: Dict[int, ProjectedLine], consensus: Dict[str, Consensus]
) -> List[Consensus]:
    """Consensus players our model has no projection for.

    These are the model's blind spot — rookies and anyone without usable NBA
    history — and they are exactly the players a draft turns on.
    """
    known = {normalize_name(line.name) for line in projections.values()}
    return [
        entry
        for key, entry in consensus.items()
        if key not in known and entry.source_count >= MIN_SOURCES_FOR_ROOKIE
    ]


def as_export_rows(entries: Sequence[Consensus]) -> List[Dict[str, object]]:
    """Render consensus players as rows the export layer can merge.

    Written in the overrides format so they land in the CSV alongside the
    model's own output, tagged with their source so it stays obvious which
    players came from outside.
    """
    rows: List[Dict[str, object]] = []
    for entry in entries:
        if not entry.games or entry.games <= 0:
            continue
        row: Dict[str, object] = {
            "nba_id": "",
            "yahoo_id": "",
            "name": entry.name,
            "team": entry.team,
            "positions": entry.positions,
            "gp": round(entry.games, 1),
            "mpg": round(entry.minutes_per_game or 0.0, 1),
            "source": "consensus:" + "+".join(sorted(set(entry.sources))),
            "confidence": round(min(entry.source_count / 3.0, 1.0), 3),
        }
        for stat in STAT_COLUMNS:
            row[stat] = round(entry.per_game.get(stat, 0.0), 3)
        fga, fta = row["fga"], row["fta"]
        row["fg_pct"] = round(row["fgm"] / fga, 4) if fga else 0.0
        row["ft_pct"] = round(row["ftm"] / fta, 4) if fta else 0.0
        rows.append(row)
    return rows
