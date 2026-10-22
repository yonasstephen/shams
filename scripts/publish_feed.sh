#!/usr/bin/env bash
#
# Publish the static NBA feed the season extension reads.
#
# Builds the feed into an orphan `feed` branch and pushes it, so the files are
# served by raw.githubusercontent.com with no server to run and no history to
# carry. Run it after the nightly /refresh, on whichever machine holds ~/.shams.
#
# Usage:
#   ./scripts/publish_feed.sh 2026-27
#   ./scripts/publish_feed.sh 2026-27 --dry-run
#
set -euo pipefail

SEASON="${1:-}"
DRY_RUN="${2:-}"

if [[ -z "$SEASON" ]]; then
  echo "usage: $0 <season> [--dry-run]   e.g. $0 2026-27" >&2
  exit 2
fi

BRANCH="feed"
REMOTE="origin"
REPO_ROOT="$(git rev-parse --show-toplevel)"
WORKTREE="$(mktemp -d "${TMPDIR:-/tmp}/shams-feed.XXXXXX")"

cleanup() {
  git -C "$REPO_ROOT" worktree remove --force "$WORKTREE" >/dev/null 2>&1 || true
  rm -rf "$WORKTREE"
}
trap cleanup EXIT

cd "$REPO_ROOT"

# Attach the worktree to the existing feed branch, or start it as an orphan so the
# data branch never carries the source history.
git fetch --quiet "$REMOTE" "$BRANCH" 2>/dev/null || true
if git show-ref --quiet "refs/remotes/$REMOTE/$BRANCH"; then
  git worktree add --quiet -B "$BRANCH" "$WORKTREE" "$REMOTE/$BRANCH"
else
  git worktree add --quiet --detach "$WORKTREE"
  git -C "$WORKTREE" checkout --quiet --orphan "$BRANCH"
  git -C "$WORKTREE" rm -rq --cached . 2>/dev/null || true
  find "$WORKTREE" -mindepth 1 -maxdepth 1 ! -name '.git' -exec rm -rf {} +
fi

pipenv run python scripts/build_feed.py "$SEASON" --out "$WORKTREE"

cd "$WORKTREE"
git add -A

if git diff --cached --quiet; then
  echo "feed unchanged — nothing to publish"
  exit 0
fi

if [[ "$DRY_RUN" == "--dry-run" ]]; then
  echo "--dry-run: would commit and push these changes to $REMOTE/$BRANCH"
  git diff --cached --stat
  exit 0
fi

git commit --quiet -m "feed: $SEASON $(date -u +%Y-%m-%dT%H:%MZ)"
git push --quiet "$REMOTE" "$BRANCH"

SLUG="$(git -C "$REPO_ROOT" remote get-url "$REMOTE" | sed -E 's#(git@github.com:|https://github.com/)##; s#\.git$##')"
echo "published to $REMOTE/$BRANCH"
echo "  https://raw.githubusercontent.com/$SLUG/$BRANCH/meta.json"
