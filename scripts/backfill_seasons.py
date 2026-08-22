#!/usr/bin/env python
"""Backfill the box score cache for past NBA seasons.

The draft assistant's projection model trains on historical per-game box scores.
The cache is already season-scoped (``~/.shams/boxscores/{games,players,season_stats}/<season>/``),
so this is a driver around the existing refresh path rather than new cache code.

Only fantasy-eligible games are cached: ``schedule_refresh`` filters via
``is_fantasy_eligible_game`` before writing, and playoffs/preseason default to off,
so the training set is regular-season-only without extra work here.

The job is long (hours) and resumable: ``refresh_boxscores`` skips games already on
disk, so re-running after an interruption picks up where it left off.

Usage:
    pipenv run python scripts/backfill_seasons.py --seasons 5
    pipenv run python scripts/backfill_seasons.py --season 2023-24 --season 2024-25
    pipenv run python scripts/backfill_seasons.py --seasons 5 --dry-run
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date
from pathlib import Path
from typing import List

# Allow running as a plain script from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.console import Console

from tools.boxscore import boxscore_cache, boxscore_refresh
from tools.utils.season import get_current_season

_console = Console()

# NBA regular seasons end in mid-April. Fetching through April 30 covers the
# regular season without reaching into the playoffs (which the schedule filter
# would exclude anyway).
_SEASON_END_MONTH = 4
_SEASON_END_DAY = 30

# ``boxscore_refresh.get_season_start_date`` hardcodes October 21, but real
# openers move: 2021-22 tipped off October 19 and 2020-21 not until December 22.
# Starting from October 1 cannot miss an opener, and costs nothing — the fetcher
# walks the schedule's own date→games map, so days without games are skipped.
_SEASON_START_MONTH = 10
_SEASON_START_DAY = 1


def _season_start_year(season: str) -> int:
    """Return the first year of a season string such as ``2023-24``."""
    try:
        return int(season.split("-")[0])
    except (ValueError, IndexError) as exc:
        raise ValueError(f"Malformed season string: {season!r}") from exc


def _format_season(start_year: int) -> str:
    """Build a season string (``2023`` -> ``2023-24``)."""
    return f"{start_year}-{str(start_year + 1)[-2:]}"


def recent_seasons(count: int, through: str) -> List[str]:
    """Return ``count`` season strings ending at ``through``, oldest first.

    Args:
        count: How many seasons to include.
        through: Most recent season to include (e.g. ``2025-26``).

    Returns:
        Season strings ordered oldest to newest.
    """
    last_year = _season_start_year(through)
    return [_format_season(y) for y in range(last_year - count + 1, last_year + 1)]


def season_start_date(season: str) -> date:
    """Return a start date guaranteed to precede the season opener."""
    return date(_season_start_year(season), _SEASON_START_MONTH, _SEASON_START_DAY)


def season_end_date(season: str, today: date) -> date:
    """Return the date to fetch through for a season.

    Completed seasons stop at the end of the regular season. The in-progress
    season stops at today, since later games have not been played.
    """
    end = date(_season_start_year(season) + 1, _SEASON_END_MONTH, _SEASON_END_DAY)
    return min(end, today)


def cached_game_count(season: str) -> int:
    """Count games already cached for a season, for progress reporting."""
    games_dir = boxscore_cache.get_cache_dir() / "games" / season
    if not games_dir.exists():
        return 0
    return sum(1 for _ in games_dir.glob("*.json"))


def backfill_season(season: str, today: date, dry_run: bool = False) -> dict:
    """Fetch and cache all regular-season box scores for one season.

    Args:
        season: Season string (e.g. ``2023-24``).
        today: Current date, injected so the cutoff logic stays testable.
        dry_run: If True, report what would be fetched without fetching.

    Returns:
        Summary dict from ``refresh_boxscores``, or a stub when ``dry_run``.
    """
    start = season_start_date(season)
    end = season_end_date(season, today)
    before = cached_game_count(season)

    _console.print(
        f"\n[bold cyan]{season}[/bold cyan]  "
        f"{start.isoformat()} → {end.isoformat()}  "
        f"([dim]{before} games already cached[/dim])"
    )

    if dry_run:
        return {"season": season, "dry_run": True, "games_cached_before": before}

    started = time.monotonic()
    summary = boxscore_refresh.refresh_boxscores(
        start_date=start, end_date=end, season=season
    )
    elapsed = time.monotonic() - started

    after = cached_game_count(season)
    _console.print(
        f"[green]✓[/green] {season}: "
        f"{summary.get('games_fetched', 0)} fetched, "
        f"{summary.get('games_failed', 0)} failed, "
        f"{after} total cached ({elapsed / 60:.1f} min)"
    )
    return summary


def _parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill the box score cache for past NBA seasons."
    )
    parser.add_argument(
        "--seasons",
        type=int,
        default=5,
        help="Number of recent seasons to backfill (default: 5).",
    )
    parser.add_argument(
        "--season",
        action="append",
        dest="explicit_seasons",
        metavar="SEASON",
        help="Backfill a specific season (repeatable). Overrides --seasons.",
    )
    parser.add_argument(
        "--through",
        default=None,
        metavar="SEASON",
        help="Most recent season to include (default: the current season).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report the date ranges that would be fetched, without fetching.",
    )
    return parser.parse_args(argv)


def main(argv: List[str] | None = None) -> int:
    """Entry point."""
    args = _parse_args(argv)
    today = date.today()
    through = args.through or get_current_season()

    if args.explicit_seasons:
        seasons = args.explicit_seasons
    else:
        seasons = recent_seasons(args.seasons, through)

    _console.print(
        f"[bold]Backfilling {len(seasons)} season(s):[/bold] {', '.join(seasons)}"
    )
    if args.dry_run:
        _console.print("[yellow]Dry run — no data will be fetched.[/yellow]")

    failures: List[str] = []
    for season in seasons:
        try:
            backfill_season(season, today, dry_run=args.dry_run)
        except KeyboardInterrupt:
            _console.print(
                "\n[yellow]Interrupted. Re-run to resume — cached games are skipped."
                "[/yellow]"
            )
            return 130
        except Exception as exc:  # pylint: disable=broad-except
            # One bad season should not abandon the rest of a multi-hour job.
            _console.print(f"[red]✗[/red] {season} failed: {exc}")
            failures.append(season)

    if failures:
        _console.print(f"\n[red]Failed seasons:[/red] {', '.join(failures)}")
        return 1

    _console.print("\n[green]Backfill complete.[/green]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
