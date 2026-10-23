# Shams v2: no Yahoo API key

Yahoo no longer accepts the Shams app's OAuth key and says its API is for US use only.
The v1 web app and CLI read leagues through that key, so they cannot even sign in.

The season extension never needed the key. It reads Yahoo through the signed-in browser
session, and it gets its NBA data from a static feed that needs no Yahoo access to build.
v2 makes that the main design:

```
NAS, nightly, no Yahoo               GitHub `feed` branch          Browser extension
nba_api box scores, schedule,  ──►   static .json.gz files   ──►   TS engine + Yahoo through
projections → build + publish        (raw.githubusercontent)        your session, on Yahoo's pages
```

| Piece | Where | Needs |
| --- | --- | --- |
| Feed job: `scripts/nightly_feed.py` | NAS container, `docker-compose.feed.yml` | `~/.shams`, `stats.nba.com`, a deploy key |
| Feed: `meta.json` + five `.json.gz` files | `feed` branch, [docs/season-feed.md](season-feed.md) | nothing at runtime |
| Season extension: `extension-season/` | Chrome and Firefox | a Yahoo login in the browser |

## v1 is kept, not removed

When Yahoo grants a key again, the official route should come back with a config change
rather than a rewrite. So v2 adds and removes nothing from v1:

- **Tagged.** `v1.0.0` marks `main` as it was deployed before v2.
- **Still in the tree and still tested.** That covers:
  - `tools/utils/yahoo.py`;
  - the backend's auth and routers;
  - the React app;
  - the CLI league commands;
  - `docker-compose.prod.yml`.

  v2 imports none of them. It shares only the NBA half of `tools/`: box scores, schedule,
  projections and the player index.
- **Same cache.** The feed job and the v1 backend mount the same `~/.shams`, so box scores
  refreshed by one serve the other.

To bring the official route back:

1. Put the key in `.env` (`YAHOO_CONSUMER_KEY`, `YAHOO_CONSUMER_SECRET`).
2. Run `docker-compose.prod.yml` next to the feed container, as before. The feed job keeps
   working either way.

**Reusing the official API in the extension.** Both routes reach the same Yahoo Fantasy v2
resource paths.

| Route | Endpoint | Auth |
| --- | --- | --- |
| Official | `fantasysports.yahooapis.com/fantasy/v2/league/{key}/players;...` | OAuth bearer token |
| Extension | `pub-api-rw.fantasysports.yahoo.com/fantasy/v2/...` | the browser's Yahoo cookies |

So the extension's Yahoo client (`extension-season/src/yahoo/`) could move to the official
endpoint by swapping how a request is sent. Check the parsers too: the extension asks for
`format=json_f`, and the response shape may differ from the official API's `format=json`.

## The feed job

Each run does the following, with no Yahoo calls:

1. **Refresh new games:** `boxscore_refresh.smart_refresh`, from the last cached day to today.
2. **Fill gaps:** `boxscore_refresh.fill_missing_games` fetches any finished game the cache
   still lacks. Examples are a game that failed to fetch, or an opening night before the
   first cached day.
3. **Build:** `scripts/build_feed.py`, anchored to the Eastern date.
4. **Publish:** `scripts/publish_feed.py` replaces the `feed` branch with a single commit.
   It refuses two kinds of build:
   - **unchanged:** a build whose files match the live feed is skipped;
   - **shrunk:** a build where data the live feed had for this season dropped to zero.

The season follows the date (`get_current_season`), so October rolls it over without a
config change.

**Failures.** In daily mode a failed run is retried after an hour, up to three tries, and
then left for the next day. A refused publish is not retried, because the same data would
be refused again.

### Setting it up on the NAS

The NAS runs its own compose file, so copy the `feed` service from
`docker-compose.feed.yml` into it.

1. **Deploy key.** Create a key with write access to this repository only:

   ```bash
   mkdir -p secrets && ssh-keygen -t ed25519 -N "" -C shams-feed -f secrets/feed_deploy_key
   cat secrets/feed_deploy_key.pub
   ```

   Add the public key at <https://github.com/yonasstephen/shams/settings/keys> with
   **Allow write access** ticked. `secrets/` is gitignored.

2. **Cache volume.** Map `/root/.shams` to the same host directory the backend service uses.

3. **Image.**
   - `ghcr.io/yonasstephen/shams-feed:latest` is published by `.github/workflows/docker.yml`
     on push to `main`, like the other two images.
   - Until this branch is merged, build it on the NAS instead with
     `docker build -f feed-job/Dockerfile -t ghcr.io/yonasstephen/shams-feed:latest .`
   - If the NAS cannot pull it after a merge, give the `shams-feed` package the same
     visibility as `shams-backend` on GitHub.

4. **First run.** Run it once now, then leave it on its daily schedule (05:00 Eastern):

   ```bash
   docker compose run --rm feed python scripts/nightly_feed.py
   docker compose up -d feed
   docker compose logs -f feed
   ```

**If a publish is refused** because a count would drop to zero, the NAS cache is missing
data the live feed was built with. Usually that is one of:

- the projections CSV in `~/.shams/projections/`;
- last season's box scores.

Copy them over from the machine that built the live feed. Pass `--allow-shrink` to
`publish_feed.py` only when losing them is intended.

### By hand

`./scripts/publish_feed.sh <season> [--dry-run]` still works from a laptop. It now uses
the same publisher, so it also replaces the branch with one commit.

## What comes next

1. **The feed job** (this change). It keeps the extension current through the season.
2. **A multi-league home** on Yahoo's basketball home page, which already lists every team.
   It has to live on a Yahoo page, because Yahoo's API answers only its own origin. It
   replaces the web app's Home and Matchup pages and the CLI's `/matchup-all`.
3. **The engine**:
   - win probability per category;
   - simulating an add together with its drop;
   - league settings: scoring type, add limits, games-played caps.

   Claude's advice is built on top of these, with the user's own Anthropic key.
4. **Stop running v1 on the NAS.** Its code stays, as described above. The draft assistant
   can read `projections.json.gz` from the feed instead of the backend.
