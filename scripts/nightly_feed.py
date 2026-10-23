#!/usr/bin/env python
"""Nightly job: refresh NBA box scores, then publish the season extension's feed.

Everything here is NBA data from nba_api, so it needs no Yahoo access and no API key,
only the ``~/.shams`` cache and a way to push the ``feed`` branch. It is what the NAS's
``feed`` container runs (docker-compose.feed.yml; see docs/shams-v2.md):

    python scripts/nightly_feed.py              # once, now
    python scripts/nightly_feed.py --at 05:00   # every day at 05:00 US Eastern

The season follows the date, so the job rolls into a new season each October without
a config change. On the daily schedule a run that fails is retried an hour later, up to
three tries, and then left for the next day; the live feed stays as it was rather than
being replaced by a partial build. A one-off run tries once.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import traceback
from datetime import datetime, time as clock, timedelta
from pathlib import Path
from typing import Callable, Dict, Optional, Sequence

import pytz

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# pylint: disable=wrong-import-position
from scripts import publish_feed
from tools.boxscore import boxscore_refresh
from tools.utils.season import get_current_season

# pylint: enable=wrong-import-position

#: NBA days, game times and "final by morning" are all Eastern.
EASTERN = pytz.timezone("US/Eastern")

ATTEMPTS = 3
RETRY_DELAY = timedelta(hours=1)


def log(message: str) -> None:
    """A timestamped line, flushed so ``docker logs`` shows it as it happens."""
    print(f"[{datetime.now(EASTERN):%Y-%m-%d %H:%M:%S %Z}] {message}", flush=True)


def refresh(season: str) -> Dict[str, Dict]:
    """Bring the box score cache up to date: new days first, then any gaps behind them."""
    latest = boxscore_refresh.smart_refresh(season)
    gaps = boxscore_refresh.fill_missing_games(season)
    return {"latest": latest, "gaps": gaps}


def run_once(remote: str, *, dry_run: bool, ssh_key: Optional[str]) -> str:
    """Refresh and publish the current season; return the publish log line."""
    season = get_current_season()
    log(f"refreshing {season} box scores")
    result = refresh(season)

    latest, gaps = result["latest"], result["gaps"]
    log(
        f"fetched {latest.get('games_fetched', 0)} games "
        f"({latest.get('start_date')} to {latest.get('end_date')}), "
        f"{latest.get('games_failed', 0)} failed"
    )
    if gaps["dates"]:
        log(
            f"filled gaps on {len(gaps['dates'])} earlier days ({', '.join(gaps['dates'][:5])}"
            f"{', ...' if len(gaps['dates']) > 5 else ''}): {gaps['games_fetched']} games fetched, "
            f"{gaps['games_failed']} still failing"
        )

    status, meta = publish_feed.publish(
        season,
        remote,
        datetime.now(EASTERN).date(),
        dry_run=dry_run,
        ssh_key=ssh_key,
    )
    return publish_feed.describe(status, meta, publish_feed.BRANCH)


def next_run(now: datetime, at: clock) -> datetime:
    """The first ``at`` (US Eastern wall clock) strictly after ``now``, an aware datetime."""
    day = now.astimezone(EASTERN).date()
    candidate = EASTERN.localize(datetime.combine(day, at))
    if candidate <= now:
        candidate = EASTERN.localize(datetime.combine(day + timedelta(days=1), at))
    return candidate


def run_with_retries(
    job: Callable[[], str],
    attempts: int,
    sleep: Callable[[float], None] = time.sleep,
) -> bool:
    """Run ``job`` up to ``attempts`` times, an hour apart; True once it succeeds."""
    for attempt in range(1, attempts + 1):
        try:
            log(job())
            return True
        except publish_feed.PublishError as err:
            # A guard refused the build; the same data will be refused again in an hour.
            log(f"not published: {err}")
            return False
        except Exception:  # pylint: disable=broad-exception-caught
            # nba_api timeouts, a network blip on push: anything else may pass next time.
            log(f"attempt {attempt}/{attempts} failed:\n{traceback.format_exc().rstrip()}")
            if attempt < attempts:
                sleep(RETRY_DELAY.total_seconds())
    return False


def run_daily(at: clock, job: Callable[[], str]) -> None:
    """Run ``job`` every day at ``at`` US Eastern, forever."""
    while True:
        when = next_run(datetime.now(EASTERN), at)
        log(f"next run at {when:%Y-%m-%d %H:%M %Z}")
        time.sleep(max(0.0, (when - datetime.now(EASTERN)).total_seconds()))
        run_with_retries(job, ATTEMPTS)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--at",
        help="Run every day at HH:MM US Eastern instead of once now (box scores are final by ~03:00)",
    )
    parser.add_argument("--remote", help="Git remote to publish to (default: $SHAMS_FEED_REMOTE, else origin)")
    parser.add_argument("--dry-run", action="store_true", help="Refresh and build, but do not push")
    args = parser.parse_args(argv)

    remote = args.remote or publish_feed.default_remote()
    if not remote:
        print("ERROR: no remote: pass --remote or set SHAMS_FEED_REMOTE", file=sys.stderr)
        return 2

    def job() -> str:
        return run_once(remote, dry_run=args.dry_run, ssh_key=os.environ.get("SHAMS_FEED_SSH_KEY"))

    if args.at:
        try:
            at = clock.fromisoformat(args.at)
        except ValueError:
            print(f"ERROR: --at wants HH:MM, got {args.at!r}", file=sys.stderr)
            return 2
        run_daily(at, job)
        return 0

    return 0 if run_with_retries(job, attempts=1) else 1


if __name__ == "__main__":
    sys.exit(main())
