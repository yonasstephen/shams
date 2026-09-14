"""Export projections to CSV, with a hand-editable override layer.

The CSV is the seam between the offline model and the live draft assistant.
Nothing downstream knows or cares how the numbers were produced, which is what
lets Yahoo's projections, our model, or a blend of both be swapped without
touching the draft path.

Percentage categories are stored as makes **and** attempts, never as a bare
ratio. A team's FG% is total makes over total attempts, so a projection that
throws away volume cannot be aggregated correctly.

The overrides file is deliberately separate and applied last. Rookies, trades
and role changes are exactly what a history-based model cannot see, and they are
also exactly what decides a draft — so there has to be a place to put a human
read that survives regenerating the model.
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from tools.projections.marcel import ProjectedLine

logger = logging.getLogger(__name__)

#: Column order. Stable, because the overrides file is edited by hand against it.
COLUMNS = (
    "nba_id",
    "yahoo_id",
    "name",
    "team",
    "positions",
    "gp",
    "mpg",
    "fgm",
    "fga",
    "fg_pct",
    "ftm",
    "fta",
    "ft_pct",
    "threes",
    "points",
    "rebounds",
    "assists",
    "steals",
    "blocks",
    "turnovers",
    "source",
    "confidence",
)

#: Per-game stat columns, in the order they appear above.
STAT_COLUMNS = (
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


def projections_dir() -> Path:
    """Where projection CSVs live."""
    directory = Path.home() / ".shams" / "projections"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def csv_path(season: str) -> Path:
    """Path of the projection CSV for a season."""
    return projections_dir() / f"{season}.csv"


def overrides_path(season: str) -> Path:
    """Path of the hand-edited overrides for a season."""
    return projections_dir() / f"{season}.overrides.csv"


@dataclass
class ExportRow:
    """One player's projected line, ready to serialize."""

    nba_id: int
    name: str
    per_game: Dict[str, float]
    games: float
    minutes_per_game: float
    yahoo_id: Optional[str] = None
    team: str = ""
    positions: str = ""
    source: str = "marcel"
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, object]:
        """Flatten into CSV columns."""
        row: Dict[str, object] = {
            "nba_id": self.nba_id,
            "yahoo_id": self.yahoo_id or "",
            "name": self.name,
            "team": self.team,
            "positions": self.positions,
            "gp": round(self.games, 1),
            "mpg": round(self.minutes_per_game, 1),
            "source": self.source,
            "confidence": round(self.confidence, 3),
        }
        for stat in STAT_COLUMNS:
            row[stat] = round(self.per_game.get(stat, 0.0), 3)
        row["fg_pct"] = round(_ratio(row["fgm"], row["fga"]), 4)
        row["ft_pct"] = round(_ratio(row["ftm"], row["fta"]), 4)
        return row


def _ratio(numerator: object, denominator: object) -> float:
    """Ratio guarding a zero denominator."""
    try:
        top, bottom = float(numerator), float(denominator)
    except (TypeError, ValueError):
        return 0.0
    return top / bottom if bottom else 0.0


def _confidence(line: ProjectedLine) -> float:
    """How much evidence stands behind a projection, in [0, 1].

    Driven by seasons of history and projected minutes: a player with three
    full seasons and a starter's workload is a much firmer projection than a
    fringe player with one thin year.
    """
    seasons = min(len(line.seasons_used), 3) / 3.0
    workload = min(line.minutes_per_game, 30.0) / 30.0
    return round(0.4 * seasons + 0.6 * workload, 3)


def build_rows(
    projections: Dict[int, ProjectedLine],
    yahoo_ids: Optional[Dict[int, str]] = None,
    teams: Optional[Dict[int, str]] = None,
    positions: Optional[Dict[int, str]] = None,
) -> List[ExportRow]:
    """Convert projections into export rows, best players first."""
    yahoo_ids = yahoo_ids or {}
    teams = teams or {}
    positions = positions or {}

    rows = [
        ExportRow(
            nba_id=line.nba_id,
            name=line.name,
            per_game=dict(line.per_game),
            games=line.games,
            minutes_per_game=line.minutes_per_game,
            yahoo_id=yahoo_ids.get(line.nba_id),
            team=teams.get(line.nba_id, ""),
            positions=positions.get(line.nba_id, ""),
            confidence=_confidence(line),
        )
        for line in projections.values()
    ]
    # Points is a crude but stable ordering; the draft engine does the real
    # valuation. Sorting only makes the file readable.
    rows.sort(key=lambda r: r.per_game.get("points", 0.0) * r.games, reverse=True)
    return rows


def write_csv(rows: Iterable[ExportRow], path: Path) -> int:
    """Write rows to ``path``.

    Returns:
        Number of rows written.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(COLUMNS))
        writer.writeheader()
        for row in rows:
            writer.writerow(row.to_dict())
            count += 1
    return count


def read_csv(path: Path) -> List[Dict[str, object]]:
    """Read a projection CSV into dicts with numeric fields coerced."""
    if not path.exists():
        return []

    numeric = set(STAT_COLUMNS) | {"gp", "mpg", "fg_pct", "ft_pct", "confidence"}
    rows: List[Dict[str, object]] = []
    with open(path, "r", encoding="utf-8", newline="") as handle:
        for raw in csv.DictReader(handle):
            row: Dict[str, object] = {}
            for key, value in raw.items():
                if key in numeric:
                    try:
                        row[key] = float(value) if value not in ("", None) else None
                    except (TypeError, ValueError):
                        row[key] = None
                else:
                    row[key] = value
            rows.append(row)
    return rows


def apply_overrides(
    rows: List[Dict[str, object]], overrides: List[Dict[str, object]]
) -> List[Dict[str, object]]:
    """Merge hand-edited overrides over generated rows.

    Matching is by ``nba_id`` when present, otherwise by normalized name. Only
    the columns actually filled in are overridden, so an override file can set
    just ``mpg`` for one player and leave everything else to the model. A row
    whose id matches nothing is appended, which is how a rookie with no history
    gets into the file at all.

    Args:
        rows: Generated projection rows.
        overrides: Rows read from the overrides CSV.

    Returns:
        The merged rows.
    """
    if not overrides:
        return rows

    by_id = {str(row.get("nba_id")): row for row in rows}
    by_name = {str(row.get("name", "")).strip().lower(): row for row in rows}

    for override in overrides:
        key = str(override.get("nba_id") or "").strip()
        target = by_id.get(key)
        if target is None:
            target = by_name.get(str(override.get("name", "")).strip().lower())

        if target is None:
            override["source"] = override.get("source") or "override"
            rows.append(override)
            by_id[key] = override
            continue

        for column, value in override.items():
            if value in ("", None):
                continue
            target[column] = value
        target["source"] = f"{target.get('source', 'marcel')}+override"

    # Percentages must follow the overridden volume, not the stale ratio.
    for row in rows:
        row["fg_pct"] = round(_ratio(row.get("fgm"), row.get("fga")), 4)
        row["ft_pct"] = round(_ratio(row.get("ftm"), row.get("fta")), 4)

    return rows


def load_projections(season: str) -> List[Dict[str, object]]:
    """Load a season's CSV with overrides applied.

    Returns an empty list when nothing has been exported, so the draft assistant
    falls back to Yahoo's projections rather than failing.
    """
    rows = read_csv(csv_path(season))
    if not rows:
        return []
    return apply_overrides(rows, read_csv(overrides_path(season)))


def write_override_template(season: str, names: Iterable[str]) -> Path:
    """Write an empty overrides file listing players, ready to fill in.

    Only ``name`` is populated; every other column is left blank so that
    anything untouched falls through to the model.
    """
    path = overrides_path(season)
    if path.exists():
        logger.info("Overrides already exist at %s; leaving it alone", path)
        return path

    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(COLUMNS))
        writer.writeheader()
        for name in names:
            writer.writerow({"name": name})
    return path
