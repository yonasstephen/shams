#!/usr/bin/env bash
#
# Publish the static NBA feed the season extension reads.
#
# A wrapper kept for muscle memory: the work is in scripts/publish_feed.py, which the
# NAS job (scripts/nightly_feed.py) calls too. It builds the feed and replaces the
# `feed` branch with a single commit, skipping the push when nothing changed.
#
# Usage:
#   ./scripts/publish_feed.sh 2026-27
#   ./scripts/publish_feed.sh 2026-27 --dry-run
#
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"
exec pipenv run python scripts/publish_feed.py "$@"
