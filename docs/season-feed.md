# The season extension's static feed

The season Chrome extension reads Yahoo directly from the browser session, so the only
thing it needs from us is NBA data. That arrives as five small files on an orphan `feed`
branch, served by `raw.githubusercontent.com` — no server at runtime, and a feed that is a
day stale still projects correctly.

## Files

| File | Contents |
| --- | --- |
| `meta.json` | schema version, season, `generated_at`, per-file sizes and sha256 |
| `projections.json.gz` | Marcel+residual per-game line for every projected player (`scripts/build_projections.py`), keyed by NBA id. The preseason and early-season baseline. |
| `players.json.gz` | Season averages plus a raw 35-day game-log tail per player |
| `players-prev.json.gz` | Previous season's averages, for players with no current-season sample |
| `schedule.json.gz` | date → `[home, away, game_id, postponed]`, by tricode |
| `player-index.json.gz` | Yahoo id → NBA id, plus NBA id → name |

The game log is shipped **raw rather than pre-averaged** on purpose: the extension computes
the `last3` / `last7` / `last7d` / `last30d` windows itself against the day it runs, so the
windows stay correct even when the feed is a couple of days behind.

Sizes: ~110 KB gzipped in the preseason, ~220 KB in season.

## Building and publishing

```bash
# once per season, before the first feed build — the schedule is not optional,
# games-remaining is pure schedule math and build_feed.py exits 1 without it
pipenv run python -c "from tools.schedule import schedule_refresh; schedule_refresh.cache_all_team_schedules('2026-27')"

pipenv run python scripts/build_feed.py 2026-27 --out /tmp/feed   # inspect locally
./scripts/publish_feed.sh 2026-27 --dry-run                       # see what would change
./scripts/publish_feed.sh 2026-27                                 # commit + push the feed branch
```

Nightly, on whichever machine holds `~/.shams` (the refresh needs `stats.nba.com`, which
blocks cloud IPs — do not move this into GitHub Actions):

```cron
30 5 * * *  cd /path/to/shams && pipenv run ./shams --refresh && ./scripts/publish_feed.sh 2026-27
```

`build_feed.py` writes byte-stable gzip (mtime zeroed), so an unchanged feed produces no
commit and no re-download for the extension.

## Rebuilding a historical feed

For parity fixtures, anchor the build to a past date; the game-log tail is bounded on both
ends, so nothing after the anchor leaks in:

```bash
pipenv run python scripts/build_feed.py 2025-26 --out /tmp/feed-jan --today 2026-01-15
```
