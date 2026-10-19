# Shams Season Assistant

A Chrome extension that puts the Shams projection engine inline on Yahoo fantasy
basketball pages, with **no server running anywhere**.

It exists as a hedge. Every season-long Shams feature currently sits behind Yahoo's OAuth
app-approval program, which is a gate of unknown duration. The browser, meanwhile, already
holds an authenticated Yahoo session — so a content script can read the league directly,
and the only thing left to supply is NBA data, which arrives as a small static file.

```
Yahoo (cookie-authenticated, in the page)  ─┐
                                            ├─→ engine runs in the extension → overlay
static feed (~110 KB gz, GitHub branch)   ──┘
```

This is a **separate extension** from `../extension` (the draft assistant), with its own
manifest, deliberately: the draft assistant must not wobble before draft day.

## What it does

| Page | Overlay |
| --- | --- |
| Team / roster | A `SHAMS` column: games remaining this week / total, colour-coded |
| Matchup | Projected per-category totals for both teams, the projected category score, banked vs remaining split, and per-player contributions |
| Matchup | Best adds: free agents ranked by the categories they would flip — and the ones they would cost you |
| Transactions | Player form for everyone added, dropped or traded: last game, last 3 or 7 games, last 7, 14 or 30 days, or season, averaged or totalled, with minutes and the minute trend, as in the web app's waiver table; plus a minutes chip beside each name |
| Trade Hub | Trade insights: any team's strengths, neutral categories, weaknesses and needs, and a league grid ranking every team by category or roster slot ([docs/trade-insights.md](../docs/trade-insights.md)) |

Projection window is switchable (season, last 3, last 7, last 7 days, last 30 days),
matching the `projection_mode` values the Python engine accepts.

## Install

```bash
npm install
npm run build        # tsc --noEmit && esbuild -> dist/
```

Then `chrome://extensions` → enable Developer mode → **Load unpacked** → pick `dist/`.

The feed URL defaults to the published branch and can be changed in the popup, which also
shows how fresh the data is.

## Develop

```bash
npm run watch   # rebuild on change; reload the extension in Chrome to pick it up
npm test        # parity + unit tests
```

## The two-engine problem

The projection math exists twice: `tools/matchup/matchup_projection.py` and `src/engine/`.
That is the price of running without a server, and it is only safe because the two are
pinned together by fixtures.

`tools/tests/test_engine_parity.py` computes answers with the **Python** engine and writes
them to `test/fixtures/`. `npm test` asserts the TypeScript produces the same numbers:
category W-L-T (including the FG%/FT% volume tiebreak), greedy roster optimization, team
totals from pooled shooting volume, rolling-window averages for real players across all
four modes, the waiver lookbacks (averaged and summed, with minutes and the minute trend),
and name normalization.

**After changing projection math on either side, regenerate and re-run both:**

```bash
cd tools/tests && pipenv run pytest test_engine_parity.py -v
cd extension-season && npm test
```

## Layout

```
src/
  background.ts      service worker: fetch, decompress and cache the feed
  feed/              feed types, cache, content-script client
  yahoo/             cookie-authenticated Yahoo client + json_f shape readers
  engine/            the ported projection engine (no DOM, no chrome APIs — testable)
  overlay/           every DOM selector lives here, so Yahoo markup changes land in one place
  content/           page entry points
  popup/             feed status and the one setting
```

`docs/season-page-recon.md` records the Yahoo endpoints and DOM anchors this depends on,
and `docs/season-feed.md` covers building and publishing the feed.

## Deliberately not here

- **No writes.** Yahoo allows a lineup-setting `PUT` with a crumb; this extension only reads.
- **No accounts, no entitlements.** It is built for one person's leagues.
- **No Yahoo host permission.** Yahoo access happens inside the content script on Yahoo's
  own origin; the only host permission is the feed.
