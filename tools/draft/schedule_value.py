"""Schedule signal for draft valuation.

Nothing in the Yahoo draft room mentions the NBA schedule, yet in a weekly-lineup
league it is worth real value: a team with more four-game weeks gives you more
usable starts from the same player.

**Why this does not use the usual player-to-team index.**
:func:`tools.schedule.schedule_cache.build_player_team_index_from_boxscores`
derives a player's team by scanning cached box scores, so in October — zero games
played — it returns nothing. The draft store already carries ``team_abbr`` for
every player, which is current and trade-accurate, so the mapping goes
abbreviation -> NBA team id -> cached team schedule instead.

The signal is applied conservatively. Every team plays 82 games, so over a full
season the schedule mostly washes out; what survives is the weekly distribution.
A large multiplier here would be dressing up noise, so the adjustment is bounded
and the underlying numbers are surfaced for the panel to show.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Dict, Optional, Sequence

from tools.schedule import schedule_cache

#: A week with this many games lets a player contribute on more days than a
#: typical active-slot crunch can absorb, which is where schedule edge lives.
HEAVY_WEEK_GAMES = 4

#: Bound on how far schedule may move a player's value, in either direction.
#: Deliberately small: the effect is real but modest, and over-weighting it would
#: let a noisy signal outrank actual production.
MAX_ADJUSTMENT = 0.04


@dataclass
class TeamSchedule:
    """Schedule shape for one NBA team."""

    team_abbr: str
    team_id: Optional[int] = None
    games: int = 0
    weeks: int = 0
    heavy_weeks: int = 0

    @property
    def games_per_week(self) -> float:
        """Average games per scoring week."""
        return self.games / self.weeks if self.weeks else 0.0

    @property
    def heavy_week_share(self) -> float:
        """Fraction of weeks with at least :data:`HEAVY_WEEK_GAMES` games."""
        return self.heavy_weeks / self.weeks if self.weeks else 0.0

    @property
    def is_known(self) -> bool:
        """Whether a schedule was actually found for this team."""
        return self.games > 0


def _team_id(abbr: str) -> Optional[int]:
    """Map an NBA team abbreviation to its team id."""
    if not abbr:
        return None
    # Private helper, but it is the canonical abbreviation map in the repo and
    # duplicating it would be a second source of truth to keep in sync.
    return schedule_cache._get_team_id_from_abbr(abbr)  # pylint: disable=protected-access


def load_team_schedule(abbr: str, season: str) -> TeamSchedule:
    """Summarize one team's cached schedule.

    Returns a zeroed :class:`TeamSchedule` when the season is not cached, so the
    caller degrades to schedule-neutral rather than failing.
    """
    schedule = TeamSchedule(team_abbr=abbr)
    team_id = _team_id(abbr)
    if team_id is None:
        return schedule
    schedule.team_id = team_id

    dates = schedule_cache.load_team_schedule(team_id, season)
    if not dates:
        return schedule

    per_week: Dict[tuple, int] = defaultdict(int)
    for value in dates:
        try:
            parsed = date.fromisoformat(str(value)[:10])
        except ValueError:
            continue
        # ISO week keys group Monday-Sunday, which is how weekly leagues score.
        per_week[parsed.isocalendar()[:2]] += 1

    schedule.games = sum(per_week.values())
    schedule.weeks = len(per_week)
    schedule.heavy_weeks = sum(
        1 for count in per_week.values() if count >= HEAVY_WEEK_GAMES
    )
    return schedule


def league_schedules(abbrs: Sequence[str], season: str) -> Dict[str, TeamSchedule]:
    """Load schedules for every team abbreviation in the pool."""
    return {abbr: load_team_schedule(abbr, season) for abbr in set(abbrs) if abbr}


def adjustments(schedules: Dict[str, TeamSchedule]) -> Dict[str, float]:
    """Per-team value multipliers derived from weekly game distribution.

    A team whose heavy-week share is above the league average gets a small
    boost, below-average a small penalty, clamped to :data:`MAX_ADJUSTMENT`.

    Args:
        schedules: Team schedules by abbreviation.

    Returns:
        Mapping of abbreviation to a multiplier near 1.0. Teams with no cached
        schedule get exactly 1.0.
    """
    known = [s for s in schedules.values() if s.is_known]
    if len(known) < 2:
        return {abbr: 1.0 for abbr in schedules}

    mean_share = sum(s.heavy_week_share for s in known) / len(known)
    spread = max(
        (abs(s.heavy_week_share - mean_share) for s in known), default=0.0
    )
    if spread <= 0:
        return {abbr: 1.0 for abbr in schedules}

    result: Dict[str, float] = {}
    for abbr, schedule in schedules.items():
        if not schedule.is_known:
            result[abbr] = 1.0
            continue
        normalized = (schedule.heavy_week_share - mean_share) / spread
        result[abbr] = 1.0 + normalized * MAX_ADJUSTMENT
    return result


def is_available(season: str) -> bool:
    """Whether a usable schedule is cached for the season.

    The upcoming season's schedule is published in August, but it still has to be
    fetched. When it is missing the assistant runs schedule-neutral and says so,
    rather than silently pretending every team is average.
    """
    full = schedule_cache.load_full_schedule(season)
    return bool(full)
