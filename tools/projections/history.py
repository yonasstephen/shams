"""Per-season historical aggregates built from the cached box scores.

``boxscore_cache.compute_and_save_all_season_stats`` already writes per-game
averages, but it drops minutes played — and a per-36 rate model needs them. It
also stores abbreviated names ("C. Paul"), which are useless for matching against
external projection sources.

This module reads the raw per-game records instead, which carry ``MIN``,
``FIRST_NAME``/``LAST_NAME``, ``TEAM_ID`` and ``IS_STARTER``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterator, List, Optional

from tools.boxscore import boxscore_cache

# Counting stats summed straight off each game record, keyed by the box score
# field name. Percentages are derived from makes/attempts, never averaged.
_COUNTING_FIELDS = {
    "fgm": "FGM",
    "fga": "FGA",
    "ftm": "FTM",
    "fta": "FTA",
    "threes": "FG3M",
    "threes_att": "FG3A",
    "points": "PTS",
    "rebounds": "REB",
    "offensive_rebounds": "OREB",
    "assists": "AST",
    "steals": "STL",
    "blocks": "BLK",
    "turnovers": "TO",
    "fouls": "PF",
}

# A player with almost no minutes produces meaningless rates; the projection
# model regresses them heavily rather than trusting the sample.
MIN_MINUTES_FOR_RATES = 100.0


def parse_minutes(value: object) -> float:
    """Parse a box score ``MIN`` value into float minutes.

    The NBA API returns minutes as ``"MM:SS"`` (e.g. ``"14:58"``), but empty
    strings and nulls appear for inactive players.

    Args:
        value: Raw ``MIN`` field from a box score record.

    Returns:
        Minutes as a float; 0.0 when unparseable.
    """
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    if not text:
        return 0.0

    if ":" in text:
        minutes, _, seconds = text.partition(":")
        try:
            return int(minutes) + int(seconds) / 60.0
        except ValueError:
            return 0.0

    try:
        return float(text)
    except ValueError:
        return 0.0


@dataclass
class SeasonLine:
    """One player's totals for one season, plus the context to project from."""

    nba_id: int
    name: str
    season: str
    games_played: int = 0
    minutes: float = 0.0
    games_started: int = 0
    team_ids: List[int] = field(default_factory=list)
    totals: Dict[str, float] = field(default_factory=dict)

    @property
    def minutes_per_game(self) -> float:
        """Average minutes per game played."""
        return self.minutes / self.games_played if self.games_played else 0.0

    @property
    def primary_team_id(self) -> Optional[int]:
        """The team the player appeared for most often this season."""
        if not self.team_ids:
            return None
        return max(set(self.team_ids), key=self.team_ids.count)

    @property
    def changed_teams(self) -> bool:
        """Whether the player appeared for more than one team."""
        return len(set(self.team_ids)) > 1

    @property
    def start_rate(self) -> float:
        """Fraction of appearances made as a starter."""
        return self.games_started / self.games_played if self.games_played else 0.0

    def per_36(self, stat: str) -> float:
        """Return a counting stat scaled to a per-36-minute rate.

        Returns 0.0 below :data:`MIN_MINUTES_FOR_RATES`, where the rate is noise.
        """
        if self.minutes < MIN_MINUTES_FOR_RATES:
            return 0.0
        return self.totals.get(stat, 0.0) * 36.0 / self.minutes

    def per_game(self, stat: str) -> float:
        """Return a counting stat as a per-game average."""
        if not self.games_played:
            return 0.0
        return self.totals.get(stat, 0.0) / self.games_played

    @property
    def fg_pct(self) -> float:
        """Field goal percentage from makes over attempts."""
        attempts = self.totals.get("fga", 0.0)
        return self.totals.get("fgm", 0.0) / attempts if attempts else 0.0

    @property
    def ft_pct(self) -> float:
        """Free throw percentage from makes over attempts."""
        attempts = self.totals.get("fta", 0.0)
        return self.totals.get("ftm", 0.0) / attempts if attempts else 0.0


def _player_files(season: str) -> Iterator[Path]:
    """Yield cached per-player game files for a season."""
    players_dir = boxscore_cache.get_cache_dir() / "players" / season
    if not players_dir.exists():
        return
    yield from players_dir.glob("*.json")


def _full_name(games: List[dict], fallback: str) -> str:
    """Recover a player's full name from game records.

    The file-level ``player_name`` is abbreviated ("C. Paul"), but each game
    record carries ``FIRST_NAME`` and ``LAST_NAME``.
    """
    for game in games:
        first = (game.get("FIRST_NAME") or "").strip()
        last = (game.get("LAST_NAME") or "").strip()
        if first and last:
            return f"{first} {last}"
    return fallback


def load_season_line(path: Path, season: str) -> Optional[SeasonLine]:
    """Build a :class:`SeasonLine` from one cached player file.

    Returns None when the file is unreadable or holds no games.
    """
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (json.JSONDecodeError, IOError):
        return None

    nba_id = data.get("player_id")
    games = data.get("games") or []
    if nba_id is None or not games:
        return None

    line = SeasonLine(
        nba_id=int(nba_id),
        name=_full_name(games, data.get("player_name", "")),
        season=season,
        totals={key: 0.0 for key in _COUNTING_FIELDS},
    )

    for game in games:
        minutes = parse_minutes(game.get("MIN"))
        # A roster spot with zero minutes is a DNP, not a game played.
        if minutes <= 0:
            continue

        line.games_played += 1
        line.minutes += minutes
        if game.get("IS_STARTER"):
            line.games_started += 1

        team_id = game.get("TEAM_ID")
        if team_id is not None:
            line.team_ids.append(int(team_id))

        for key, source_field in _COUNTING_FIELDS.items():
            try:
                line.totals[key] += float(game.get(source_field) or 0)
            except (TypeError, ValueError):
                continue

    return line if line.games_played else None


def load_season(season: str) -> Dict[int, SeasonLine]:
    """Load every player's aggregate line for one season.

    Args:
        season: Season string (e.g. ``2024-25``).

    Returns:
        Mapping of NBA player ID to :class:`SeasonLine`.
    """
    lines: Dict[int, SeasonLine] = {}
    for path in _player_files(season):
        line = load_season_line(path, season)
        if line is not None:
            lines[line.nba_id] = line
    return lines


def load_seasons(seasons: List[str]) -> Dict[str, Dict[int, SeasonLine]]:
    """Load aggregate lines for several seasons.

    Args:
        seasons: Season strings, in any order.

    Returns:
        Mapping of season string to that season's player lines.
    """
    return {season: load_season(season) for season in seasons}
