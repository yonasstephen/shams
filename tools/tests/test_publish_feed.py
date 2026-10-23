"""Tests for publishing the extension feed to its branch."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import List

import pytest

from scripts.publish_feed import PublishError, _git_env, publish_dir, shrunk_counts

LIVE_COUNTS = {
    "scheduled_games": 1230,
    "players_with_games": 400,
    "projected_players": 520,
    "previous_season_players": 590,
}


def _feed(directory: Path, payload: str, season: str = "2026-27", **counts: int) -> Path:
    """A stand-in for build_feed's output: one data file and a meta.json describing it."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "players.json.gz").write_text(payload, encoding="utf-8")
    meta = {
        "season": season,
        "generated_at": f"built for {payload}",
        "counts": {**LIVE_COUNTS, **counts},
        "files": {"players.json.gz": {"sha256": payload}},
    }
    (directory / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return directory


def _git(remote: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(remote), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _history(remote: Path) -> List[str]:
    """``<sha> <parents>`` for every commit on the feed branch, newest first."""
    return _git(remote, "log", "--format=%H %P", "feed").splitlines()


@pytest.fixture(name="remote")
def fixture_remote(tmp_path) -> Path:
    path = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--quiet", "--bare", str(path)], check=True)
    return path


@pytest.mark.unit
def test_first_publish_creates_the_branch_as_one_parentless_commit(tmp_path, remote):
    status = publish_dir(_feed(tmp_path / "a", "monday"), str(remote))

    assert status == "published"
    [commit] = _history(remote)
    assert len(commit.split()) == 1  # no parent
    assert _git(remote, "show", "feed:players.json.gz") == "monday"
    assert json.loads(_git(remote, "show", "feed:meta.json"))["season"] == "2026-27"


@pytest.mark.unit
def test_each_publish_replaces_the_branch_instead_of_growing_it(tmp_path, remote):
    publish_dir(_feed(tmp_path / "a", "monday"), str(remote))
    publish_dir(_feed(tmp_path / "b", "tuesday"), str(remote))

    assert len(_history(remote)) == 1
    assert _git(remote, "show", "feed:players.json.gz") == "tuesday"


@pytest.mark.unit
def test_unchanged_files_are_not_pushed_even_though_meta_differs(tmp_path, remote):
    publish_dir(_feed(tmp_path / "a", "monday"), str(remote))
    before = _history(remote)

    # Same file hashes, rebuilt later: only generated_at would differ.
    rebuilt = _feed(tmp_path / "b", "monday")
    meta = json.loads((rebuilt / "meta.json").read_text(encoding="utf-8"))
    meta["generated_at"] = "an hour later"
    (rebuilt / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

    assert publish_dir(rebuilt, str(remote)) == "unchanged"
    assert _history(remote) == before


@pytest.mark.unit
def test_dry_run_leaves_the_remote_alone(tmp_path, remote):
    assert publish_dir(_feed(tmp_path / "a", "monday"), str(remote), dry_run=True) == "dry-run"
    assert not _git(remote, "branch", "--list", "feed")


@pytest.mark.unit
def test_a_build_missing_data_the_live_feed_had_is_refused(tmp_path, remote):
    publish_dir(_feed(tmp_path / "a", "monday"), str(remote))

    # A machine without the projections CSV builds an otherwise healthy feed.
    thin = _feed(tmp_path / "b", "tuesday", projected_players=0)
    with pytest.raises(PublishError, match="projected_players"):
        publish_dir(thin, str(remote))
    assert _git(remote, "show", "feed:players.json.gz") == "monday"

    assert publish_dir(thin, str(remote), allow_shrink=True) == "published"
    assert _git(remote, "show", "feed:players.json.gz") == "tuesday"


@pytest.mark.unit
def test_a_feed_without_a_schedule_is_never_published(tmp_path, remote):
    with pytest.raises(PublishError, match="schedule"):
        publish_dir(_feed(tmp_path / "a", "monday", scheduled_games=0), str(remote))
    assert not _git(remote, "branch", "--list", "feed")


@pytest.mark.unit
def test_shrink_guard_only_compares_within_a_season():
    live = {"season": "2026-27", "counts": LIVE_COUNTS}

    # October: the new season has no games yet, and that is expected.
    new_season = {"season": "2027-28", "counts": {**LIVE_COUNTS, "players_with_games": 0}}
    assert shrunk_counts(live, new_season) == []

    same_season = {"season": "2026-27", "counts": {**LIVE_COUNTS, "players_with_games": 0}}
    assert shrunk_counts(live, same_season) == ["players_with_games"]
    assert shrunk_counts(None, same_season) == []


@pytest.mark.unit
def test_a_deploy_key_is_used_from_a_private_copy_outside_the_feed(tmp_path):
    """ssh rejects a group-readable key, which is how a key mounted into a container often is."""
    key = tmp_path / "mounted_key"
    key.write_text("not really a key", encoding="utf-8")
    key.chmod(0o644)
    scratch = tmp_path / "scratch"
    scratch.mkdir()

    env = _git_env(str(key), scratch)

    private = scratch / "deploy_key"
    assert private.read_text(encoding="utf-8") == "not really a key"
    assert private.stat().st_mode & 0o777 == 0o600
    assert f"-i {private}" in env["GIT_SSH_COMMAND"]
    assert "GIT_SSH_COMMAND" not in _git_env(None, scratch)
