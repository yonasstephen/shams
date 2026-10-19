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

## Trade Hub (`/nba/{league}/trade_hub`)

Verified 2026-10-17 against league 2071, signed in without Yahoo Fantasy Plus. Yahoo's help
pages describe the Trade Hub in one sentence per section; everything below comes from the
page's own API calls and its bundle (`react_fantasy_tradehub.*.js`).

### What Yahoo computes, and what it gates

Every Trade Hub insight is **positional, by roster slot** (PG, SG, G, SF, PF, F, C, Util),
counted over **starters only**. The page asks for:

```
/league/{lk};out=settings/standings/teams;out=recommended_trade_partners,standings,players;
    positional_ranks.starters_only=1;recommended_trade_partners.count=1
```

With Plus, the bundle's `PREMIUM_QUERY` adds `positional_ranks` to `out=` and asks for three
partners. Each team then carries `positional_ranks[]` entries of
`{position, grade: "strong"|"neutral"|"weak", rank, starting_players, bench_players}`.

| Section | Free | Plus |
| --- | --- | --- |
| Team analysis | team name | slots bucketed Strengths / Neutral / Weaknesses with a league rank, for any team |
| League rosters | team list | team × slot rank grid, expandable to starters and bench |
| Top 3 trade partners | partner #1 | partners #2–3 and each partner's needs |
| Players marked available | list and owner | current and projected position rank, owner's needs |
| Most traded (all Yahoo leagues, today) | trade count, owner in your league | as above |

- **Needs** (`getTeamNeeds`): up to three slots, weak ones first, padded with neutral ones.
- **Partner count is enforced by the server.** Asking for `count=3` without Plus still returns
  one `recommended_trade_partner` per team. How Yahoo matches partners is not visible.
- **Player position ranks** come from `out=ranks;ranks_by_position=season,projected_season_remaining`:
  `player_rank` entries with `rank_type` `S` (season to date) or `PSR` (projected rest of
  season) plus a `rank_position`. Without Plus the page sends `ranks_by_position=` empty.
- **Most traded**: `/game/{gk}/leagues;league_keys={lk};out=settings;/players;status=T;
  sort=transactions_trades;sort_type=transaction_trends;sort_date=today;…;out=transactions,ownership`
  — free. `transactions.trades` is the count across all Yahoo leagues today.
- **Trading block**: the same players collection with `trading_block=1;out=trading_block` — free.

Shams does not request the Plus-only fields. The extension computes its own insights from
the league's categories instead; see `docs/trade-insights.md`.

### Endpoints the extension uses

| Path | Gives |
| --- | --- |
| `/league/{lk}/teams/roster` | every roster in one call: 18 teams, each player with `selected_position` and `eligible_positions`, plus `managers[].manager.nickname` |
| `/league/{lk};out=settings` | the league's `start_date`, `end_date`, `num_teams`; the settings' `trade_end_date` and `playoff_start_week` |

### DOM anchors

`#trade_hub` (inside `#yspmaincontent`) is the React mount point. It is server-rendered
empty, shows a spinner while the bundle fetches, and sometimes sits on that spinner until a
reload. Once rendered, sections carry stable `data-tst` hooks: `hub-team-analysis`,
`hub-league-rosters`, `hub-league-roster-row-{team_key}`, `hub-ideal-trade-partners-*`,
`hub-trading-block`, `hub-trading-block-player-row-{player_key}`.

The Shams panel is inserted **before** `#trade_hub`, not inside it, so React never owns or
re-renders it and the panel does not wait for Yahoo's spinner.

## League transactions (`/nba/{league}/transactions`)

Server-rendered, no React and no API call needed: the page itself names every player and
his Yahoo id. Filters (`?transactionsfilter=add|drop|trade|faab`) and paging ("Next 25")
are full page loads, so the overlay reads the table once at load.

- `table.Tst-transaction-table`, inside a `div.Mod`, after the `Tst-transaction-nav` tabs.
  One `tbody > tr` per transaction, newest first.
- Players are plain links to `https://sports.yahoo.com/nba/players/{yahoo_id}`; the news
  icon beside each is also a link (`…/players/{id}/news`, class `playernote`) and has to be
  told apart.
- **Add/drop rows**: each player sits in a `div.Pbot-xs` with `span.F-position`
  ("TOR - PG,SG"), an optional `span.F-injury` ("Q", "O"…) and an `h6` naming the source or
  destination ("Free Agent", "Waivers", "To Waivers"). The first cell holds one icon per
  player, in player order, titled "Added Player" or "Dropped Player".
- **Trade rows**: the first cell is a `rowspan` with `span.F-trade` and no title, so the
  second row of a trade has no icon cell at all. Players sit in a `p`; a cell reads
  "Traded to".
- The last cell names the fantasy team (`span.Grid-u > a`; `.Tst-team-name` on add/drop
  rows only) and the time (`.F-timestamp`, "Oct 18, 11:29 am").

The Shams panel goes before the `div.Mod`; the minutes chips go after each player's
injury tag, or his position when he has none.
