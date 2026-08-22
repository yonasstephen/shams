"""Import projections from any CSV export.

Every projection service exports a CSV, but no two agree on column names — one
says ``PTS``, another ``points``, a third ``Points/G``. Rather than a parser per
service, this resolves columns by alias, so a new source usually needs a couple
of entries in :data:`ALIASES` rather than any new code.

Totals-vs-per-game is detected rather than configured, because getting it wrong
silently produces projections that are off by a factor of seventy.
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from tools.projections.sources.base import EXTERNAL_STATS, ExternalProjection

logger = logging.getLogger(__name__)

#: Column aliases, lowercased and stripped of punctuation.
ALIASES: Dict[str, Sequence[str]] = {
    "name": ("name", "player", "playername", "fullname", "player name"),
    "team": ("team", "tm", "teamabbr", "nbateam"),
    "positions": ("pos", "position", "positions", "eligiblepositions"),
    "games": ("gp", "g", "games", "gamesplayed"),
    "minutes_per_game": ("mpg", "min", "minutes", "minutespergame"),
    "fgm": ("fgm", "fg", "fieldgoalsmade"),
    "fga": ("fga", "fieldgoalsattempted"),
    "ftm": ("ftm", "ft", "freethrowsmade"),
    "fta": ("fta", "freethrowsattempted"),
    "threes": ("3pm", "3ptm", "threes", "fg3m", "3s", "threepointersmade"),
    "points": ("pts", "points", "p"),
    "rebounds": ("reb", "rebounds", "trb", "r"),
    "assists": ("ast", "assists", "a"),
    "steals": ("stl", "st", "steals", "s"),
    "blocks": ("blk", "blocks", "b"),
    "turnovers": ("to", "tov", "turnovers"),
}

#: Above this per-game points value the column is obviously a season total.
#: Nobody averages 60 a game; plenty of players score 1,500 in a season.
_TOTALS_THRESHOLD = 60.0


def _canonical(column: str) -> str:
    """Reduce a header to its comparable form."""
    return "".join(ch for ch in column.lower() if ch.isalnum())


def _resolve_columns(headers: Sequence[str]) -> Dict[str, str]:
    """Map our field names onto this file's headers."""
    lookup = {_canonical(header): header for header in headers}
    resolved: Dict[str, str] = {}
    for field_name, aliases in ALIASES.items():
        for alias in aliases:
            header = lookup.get(_canonical(alias))
            if header is not None:
                resolved[field_name] = header
                break
    return resolved


def _to_float(value: object) -> Optional[float]:
    """Parse a CSV cell to float, tolerating blanks and stray symbols."""
    if value is None:
        return None
    text = str(value).strip().replace("%", "").replace(",", "")
    if not text or text in {"-", "--", "N/A", "NA"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


class CsvImportSource:
    """Reads projections from a CSV export."""

    def __init__(self, path: Path, name: Optional[str] = None):
        self.path = Path(path)
        self.name = name or self.path.stem

    def load(self) -> List[ExternalProjection]:
        """Parse the file into normalized projections.

        Returns an empty list when the file is missing or has no recognizable
        name column, so one broken source never takes the ensemble down.
        """
        if not self.path.exists():
            logger.warning("Projection source %s not found: %s", self.name, self.path)
            return []

        with open(self.path, "r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = reader.fieldnames or []
            columns = _resolve_columns(headers)
            if "name" not in columns:
                logger.warning(
                    "Source %s has no recognizable name column (headers: %s)",
                    self.name,
                    headers,
                )
                return []
            rows = list(reader)

        projections = [self._parse_row(row, columns) for row in rows]
        parsed = [entry for entry in projections if entry is not None]

        if self._looks_like_totals(parsed):
            logger.info("Source %s appears to hold season totals; converting", self.name)
            parsed = [self._to_per_game(entry) for entry in parsed]

        usable = [entry for entry in parsed if entry.is_usable]
        logger.info("Source %s: %d usable of %d rows", self.name, len(usable), len(rows))
        return usable

    def _parse_row(
        self, row: Dict[str, str], columns: Dict[str, str]
    ) -> Optional[ExternalProjection]:
        """Convert one CSV row."""
        name = (row.get(columns["name"]) or "").strip()
        if not name:
            return None

        entry = ExternalProjection(name=name, source=self.name)
        if "team" in columns:
            entry.team = (row.get(columns["team"]) or "").strip()
        if "positions" in columns:
            entry.positions = (row.get(columns["positions"]) or "").strip()
        if "games" in columns:
            entry.games = _to_float(row.get(columns["games"]))
        if "minutes_per_game" in columns:
            entry.minutes_per_game = _to_float(row.get(columns["minutes_per_game"]))

        for stat in EXTERNAL_STATS:
            if stat in columns:
                value = _to_float(row.get(columns[stat]))
                if value is not None:
                    entry.per_game[stat] = value
        return entry

    @staticmethod
    def _looks_like_totals(entries: Sequence[ExternalProjection]) -> bool:
        """Detect a file of season totals rather than per-game averages."""
        points = [
            entry.per_game["points"]
            for entry in entries
            if entry.per_game.get("points") is not None
        ]
        if not points:
            return False
        points.sort(reverse=True)
        # Use a high percentile rather than the max, so one junk row cannot
        # flip the whole file.
        sample = points[min(len(points) - 1, 4)]
        return sample > _TOTALS_THRESHOLD

    @staticmethod
    def _to_per_game(entry: ExternalProjection) -> ExternalProjection:
        """Divide season totals by games played."""
        if not entry.games or entry.games <= 0:
            return entry
        entry.per_game = {
            stat: value / entry.games for stat, value in entry.per_game.items()
        }
        return entry
