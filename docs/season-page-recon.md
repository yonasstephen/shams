# Yahoo season-page recon

Companion to `docs/draft-room-recon.md`, for the season-long pages the
`extension-season/` overlay injects into. Verified 2026-09-20 against league 2071
(`game_key` 478, NBA 2026-27).

## The headline: Yahoo's own API answers a cookie

A content script running on `basketball.fantasysports.yahoo.com` can call Yahoo's public
fantasy API with the user's session cookies. **No OAuth app, no consumer key, no approval
program.** This is what makes the extension a viable hedge.

```js
fetch("https://pub-api-rw.fantasysports.yahoo.com/fantasy/v2/<path>?format=json_f",
      { credentials: "include" })
```

Verified 200s, from the page, signed in as a normal user:

| Path | Gives |
| --- | --- |
| `/users;use_login=1/games;game_codes=nba` | the game key — **derive it, never hardcode it** |
| `/users;use_login=1/teams;game_keys={gk}` | the user's teams, so we know which team is theirs |
| `/league/{lk};out=settings` | stat categories (ids, sort order, display-only flags), roster slots |
| `/team/{tk}/matchups` | week number, `week_start`, `week_end`, both teams and Yahoo's own totals |
| `/team/{tk}/roster;date=YYYY-MM-DD` | roster as of that date (future dates return today's) |
| `/team/{tk}/roster/players;out=stats;type=week;week=N` | per-player banked stats for the week |
| `/league/{lk}/players;status=A;sort=AR` | free agents |

`format=json_f` returns collections as arrays of single-key wrappers
(`[{team: {...}}, …]`); `src/yahoo/shapes.ts` reads both that and the older count-keyed
form so a shape change degrades to an empty list instead of throwing.

Writes are possible too — WZRD ships a `PUT /team/{tk}/roster?crumb=…` for its one-click
lineup start — but the Shams extension is read-only and should stay that way unless
that is a deliberate decision.

## DOM anchors

Season pages are server-rendered tables, not the draft client's React/Redux app, so the
fiber-store technique from `docs/draft-room-recon.md` does not transfer. Selectors:

| Page | Anchor | Notes |
| --- | --- | --- |
| Team `/nba/{league}/{team}` | `#statTable0` | Two header rows: a group row and the label row. Player cell is `td.player`; every roster row carries **`data-ys-playerid`**, which is the clean join key. |
| Matchup `/nba/{league}/matchup` | first `table.Datatable` whose first header is `Team` and which has no `Win %` column | The `Win %` test is what distinguishes Yahoo's own totals table from WZRD's look-alike, if that extension is also installed. |
| Matchup player tables | `#statTable3` | One table holding **both** teams side by side, headers duplicated. The Shams panel renders its own per-player lists rather than threading cells into this. |

The NBA team abbreviation is only in the player cell's text (`"CLE - PG,SG"`), so it is
read with `/\b([A-Z]{2,3})\s+-\s+[A-Z]/`.

## Joining Yahoo players to NBA stats

`~/.shams/player_index.json` maps Yahoo ids to NBA ids, but it only holds players some
past waiver or ranking run touched — **473 ids, and not one of the 15 players on the test
roster**. The Python engine does not depend on it either; `_project_player_stats` resolves
by name through `player_fetcher.player_id_lookup`.

So the feed ships a normalized-name lookup as well (808 entries), and the extension tries
the Yahoo id first, then the name. With that, 15/15 roster players resolved. Both sides
normalize identically (NFKD, strip non-ASCII, trim, lowercase) and a parity fixture holds
them together.

Yahoo is the authority on which NBA team a player is on: the projection CSV was built in
August and still had Harden on LAC, Ingram on TOR. The engine reads `editorial_team_abbr`
from Yahoo for every schedule lookup and only takes per-game averages from the feed.

## Cross-check

With the same league and week, the games-remaining column agreed with WZRD's own column on
all 15 players (2/2, 3/3, …), which is a useful independent check of the schedule math.
