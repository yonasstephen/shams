#!/usr/bin/env python
"""Publish the season extension's NBA feed to the repo's ``feed`` branch.

Builds the feed (``scripts/build_feed.py``) and pushes it as the branch's only commit,
so raw.githubusercontent.com serves it with no server to run. Each publish replaces the
last: the branch holds the latest feed and no history. A past feed can always be rebuilt
from the cache with ``build_feed.py --today``, so a season of nightly snapshots would
only make every clone of the repo heavier.

It works from a scratch repository rather than this checkout, so it runs the same on a
laptop and in the NAS container, which has no checkout at all.

Two guards keep a bad build off the branch:

* a feed whose files hash the same as the live one is not pushed, and
* a build that comes out empty where the live feed for the same season had data (a
  machine without the projections CSV or last season's box scores, say) is refused
  unless ``--allow-shrink`` says that is intended.

Usage:
    pipenv run python scripts/publish_feed.py 2026-27
    pipenv run python scripts/publish_feed.py 2026-27 --dry-run

The remote is ``--remote``, else ``$SHAMS_FEED_REMOTE``, else this checkout's ``origin``.
``$SHAMS_FEED_SSH_KEY`` names a deploy key to push with, as the NAS job does.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import build_feed  # pylint: disable=wrong-import-position
from tools.utils.season import get_current_season  # pylint: disable=wrong-import-position

REPO_ROOT = Path(__file__).resolve().parent.parent

BRANCH = "feed"

#: The feed is data, not source: commit it under a fixed bot identity so the job needs
#: no git config on the machine it runs on.
COMMITTER = {
    "GIT_AUTHOR_NAME": "shams feed",
    "GIT_AUTHOR_EMAIL": "feed@shams.invalid",
    "GIT_COMMITTER_NAME": "shams feed",
    "GIT_COMMITTER_EMAIL": "feed@shams.invalid",
}


class PublishError(RuntimeError):
    """The feed was not published, and retrying will not change that."""


def _git(repo: Path, args: Sequence[str], env: Dict[str, str]) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {args[0]} failed: {result.stderr.strip() or result.stdout.strip()}")
    return result.stdout.strip()


def _git_env(ssh_key: Optional[str], scratch: Path) -> Dict[str, str]:
    env = {**os.environ, **COMMITTER, "GIT_TERMINAL_PROMPT": "0"}
    if ssh_key:
        # ssh refuses a key that others can read, and a key mounted into a container
        # often is, so push with a private copy instead.
        private = scratch / "deploy_key"
        shutil.copyfile(ssh_key, private)
        private.chmod(0o600)
        env["GIT_SSH_COMMAND"] = (
            f"ssh -i {shlex.quote(str(private))} -o IdentitiesOnly=yes -o BatchMode=yes"
        )
    return env


def default_remote() -> Optional[str]:
    """``$SHAMS_FEED_REMOTE``, else the ``origin`` of the checkout this script is in."""
    if os.environ.get("SHAMS_FEED_REMOTE"):
        return os.environ["SHAMS_FEED_REMOTE"]
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "remote", "get-url", "origin"],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() or None


def _live_feed(
    repo: Path, remote: str, branch: str, env: Dict[str, str]
) -> Tuple[Optional[str], Optional[Dict]]:
    """The live branch's commit and its meta.json, or ``(None, None)`` before the first publish."""
    heads = _git(repo, ["ls-remote", remote, f"refs/heads/{branch}"], env)
    if not heads:
        return None, None
    sha = heads.split()[0]
    _git(repo, ["fetch", "--quiet", "--depth", "1", remote, f"refs/heads/{branch}"], env)
    try:
        return sha, json.loads(_git(repo, ["show", f"{sha}:meta.json"], env))
    except (RuntimeError, json.JSONDecodeError):
        return sha, None


def shrunk_counts(live: Optional[Dict], built: Dict) -> List[str]:
    """Counts the live feed had for this season that the new build lost entirely."""
    if not live or live.get("season") != built.get("season"):
        # A new season starts thin by design; nothing to compare against.
        return []
    live_counts = live.get("counts") or {}
    return sorted(
        name for name, value in (built.get("counts") or {}).items() if not value and live_counts.get(name)
    )


def publish_dir(
    feed_dir: Path,
    remote: str,
    *,
    branch: str = BRANCH,
    dry_run: bool = False,
    allow_shrink: bool = False,
    ssh_key: Optional[str] = None,
) -> str:
    """Push the feed built in ``feed_dir`` as the only commit on ``branch``.

    Returns ``"unchanged"``, ``"dry-run"`` or ``"published"``. Raises ``PublishError``
    when a guard refuses the build, and ``RuntimeError`` when git itself fails.
    """
    meta = json.loads((feed_dir / "meta.json").read_text(encoding="utf-8"))
    if not (meta.get("counts") or {}).get("scheduled_games"):
        raise PublishError(
            f"no cached schedule for {meta.get('season')}: games remaining is pure schedule "
            "math, so this feed would be useless. Refresh the schedule first."
        )

    with tempfile.TemporaryDirectory(prefix="shams-feed-") as scratch:
        scratch_dir = Path(scratch)
        repo = scratch_dir / "repo"
        repo.mkdir()
        env = _git_env(ssh_key, scratch_dir)
        _git(repo, ["init", "--quiet"], env)

        live_sha, live_meta = _live_feed(repo, remote, branch, env)
        if live_meta and live_meta.get("season") == meta.get("season") and live_meta.get("files") == meta.get("files"):
            return "unchanged"

        shrunk = shrunk_counts(live_meta, meta)
        if shrunk and not allow_shrink:
            raise PublishError(
                f"refusing to publish: {', '.join(shrunk)} would drop to 0 from the live feed's "
                f"{', '.join(str(live_meta['counts'][name]) for name in shrunk)}. This machine's "
                "~/.shams is missing data the live feed was built with; pass --allow-shrink if "
                "that is intended."
            )

        for path in feed_dir.iterdir():
            if path.is_file():
                shutil.copy2(path, repo / path.name)
        _git(repo, ["add", "-A"], env)
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
        _git(repo, ["commit", "--quiet", "-m", f"feed: {meta['season']} {stamp}"], env)

        if dry_run:
            return "dry-run"

        # Replace the branch, but only if it is still the commit just compared against:
        # two publishers racing must not silently overwrite each other.
        lease = f"--force-with-lease=refs/heads/{branch}:{live_sha or ''}"
        _git(repo, ["push", "--quiet", lease, remote, f"HEAD:refs/heads/{branch}"], env)
        return "published"


def publish(
    season: str,
    remote: str,
    today: date,
    *,
    tail_days: int = 35,
    branch: str = BRANCH,
    dry_run: bool = False,
    allow_shrink: bool = False,
    ssh_key: Optional[str] = None,
) -> Tuple[str, Dict]:
    """Build the feed for ``season`` anchored at ``today`` and publish it.

    Returns what ``publish_dir`` did, and the built feed's meta.json.
    """
    with tempfile.TemporaryDirectory(prefix="shams-feed-build-") as out:
        meta = build_feed.build(season, Path(out), tail_days, today)
        status = publish_dir(
            Path(out),
            remote,
            branch=branch,
            dry_run=dry_run,
            allow_shrink=allow_shrink,
            ssh_key=ssh_key,
        )
    return status, meta


def describe(status: str, meta: Dict, branch: str) -> str:
    """One line for a log saying what happened, with the counts that matter."""
    counts = meta.get("counts") or {}
    summary = (
        f"{counts.get('players_with_games', 0)} players with games, "
        f"{counts.get('scheduled_games', 0)} scheduled games, "
        f"{counts.get('projected_players', 0)} projected"
    )
    verbs = {
        "unchanged": "feed unchanged, nothing pushed",
        "dry-run": f"--dry-run: would replace {branch}",
        "published": f"published to {branch}",
    }
    return f"{verbs[status]} ({meta.get('season')}: {summary})"


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("season", help=f"NBA season to publish, e.g. {get_current_season()}")
    parser.add_argument("--remote", help="Git remote URL or path (default: $SHAMS_FEED_REMOTE, else origin)")
    parser.add_argument("--branch", default=BRANCH, help=f"Branch to replace (default: {BRANCH})")
    parser.add_argument("--tail-days", type=int, default=35, help="Days of game log to carry (default: 35)")
    parser.add_argument("--today", help="Anchor date, YYYY-MM-DD (default: today)")
    parser.add_argument("--dry-run", action="store_true", help="Build and compare, but do not push")
    parser.add_argument(
        "--allow-shrink",
        action="store_true",
        help="Publish even if a count the live feed has would drop to 0",
    )
    args = parser.parse_args(argv)

    remote = args.remote or default_remote()
    if not remote:
        print("ERROR: no remote: pass --remote or set SHAMS_FEED_REMOTE", file=sys.stderr)
        return 2

    anchor = date.fromisoformat(args.today) if args.today else date.today()
    try:
        status, meta = publish(
            args.season,
            remote,
            anchor,
            tail_days=args.tail_days,
            branch=args.branch,
            dry_run=args.dry_run,
            allow_shrink=args.allow_shrink,
            ssh_key=os.environ.get("SHAMS_FEED_SSH_KEY"),
        )
    except (PublishError, RuntimeError) as err:
        print(f"ERROR: {err}", file=sys.stderr)
        return 1

    print(describe(status, meta, args.branch))
    return 0


if __name__ == "__main__":
    sys.exit(main())
