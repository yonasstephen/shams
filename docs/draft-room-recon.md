# Yahoo NBA draft room — recon findings

Captured 2026-08-22 from a live 14-team H2H mock draft (`Double Dribble - H2H`,
league 2041416, `game_season: 2026-27`).

## Entry points

| Page | URL pattern |
| --- | --- |
| Mock lobby | `basketball.fantasysports.yahoo.com/nba/<league_id>/mock_lobby` |
| Waiting room | `basketball.fantasysports.yahoo.com/nba/<league_id>/mock_waiting?mlid=<draft_id>&lobby=standard` |
| **Draft client** | `basketball.fantasysports.yahoo.com/draftclient/nba/<draft_id>/<pick_slot>?auth=<token>` |
| Pre-draft rankings | `*.fantasysports.yahoo.com/*/editprerank*` |

The lobby and waiting room are legacy YUI, server-rendered — no useful state. Only the
**draft client** matters, and it is a separate React app mounted on `#app`.

Content script glob: `*://*.fantasysports.yahoo.com/draftclient/*`

## The draft client is Redux — read the store, not the fibers

The client is modern React (`__reactFiber$…`, no `__reactInternalInstance$`, devtools hook
absent). It uses Redux, and the store object sits **31 fiber nodes from the root** at
`memoizedProps.store`.

```js
// MAIN world. Walk from any #app descendant up to the fiber root, then scan for the store.
const el = document.querySelector('#app *');
const k  = Object.keys(el).find(x => x.startsWith('__reactFiber$'));
let root = el[k]; while (root.return) root = root.return;
// scan memoizedProps/memoizedState for {getState, dispatch, subscribe}
```

This replaces the per-field fiber walking the plan assumed:

- **One lookup**, then `store.getState()` returns the entire draft state.
- `store.subscribe(cb)` gives **push updates** — no polling loop, sub-second latency.
- Robust to visual redesign: only a Redux refactor breaks it, not a re-skin.
- The adapter shrinks to "find store, map slices", which is a small, testable surface.

## State shape (`store.getState()`)

| Slice | Contents |
| --- | --- |
| `players.byId` / `players.all` | **The full pool** — 662 players, not the 100 rendered |
| `draftPicks.order` | Pick history **as objects, in pick order** — not keys. `{id, playerId, teamId, cost}` |
| `draftPicks.byId` | The same picks keyed by **`playerId`**, not by pick `id` |
| `draftOrder.order` | **Every pick of the draft up front** — 182 × `{id, teamId}` |
| `draftOrder.currentPick` / `.currentTeam` | Whose turn it is |
| `countdown.seconds` / `.timeout` | The live pick clock |
| `league.teams` | All teams + managers |
| `queue` | Your player queue |
| `settings.settings` | `roster_positions`, `stat_categories`, `draft_type`, `is_auction_draft`, `max_teams`, `game_season` |
| `settings` (top) | `league_key`, `league_id`, `num_teams`, `pickTime`, `is_mock_league` |
| `context` | `managerId` (= your team id), `leagueId`, `isPremium` |
| `auction` | `bids`, `budgets`, `nominatedPlayer`, `currentBidAmount` |
| `draftStatus` | `draftServer`, `draftPort: 443` — the dedicated socket host |
| `draftAssistant` | Yahoo's own paid Draft Scout recommendations |

### Player object

Keyed by Yahoo player id (`id: "3704"` = LeBron), with `player_key` and `team_key` also present.
**Name matching is unnecessary** — the ids join directly to `player_index.py`.

Fields that matter:

- `pos: ["SF","PF","F","Util"]` — eligible slots **already expanded to flex positions**, exactly
  what `tools/matchup/roster_optimizer.py` consumes.
- `average-pick`, `average-round`, `percent-drafted` — **live ADP**.
- `preseason-average-pick`, `preseason-percent-drafted` — **preseason ADP**.
- `auction-value`, `o_rank`, `psr_rank`, `s_rank_1`, `avg_rank_1` — Yahoo's rankings.
- `inj`, `inj_full`, `inj_note` — injury status (`GTD`, `NA`, …).
- `season_stats` — last season's totals, by stat id.
- `average_stats` — last season's per-game averages, by stat id.
- `projected_stats` — **Yahoo's 2026-27 season projections**, by stat id.

### Stat id mapping (verified against the data)

`stat_categories` in settings gives id → display name. The stat blobs are keyed by those ids:

| id | Stat | | id | Stat |
| --- | --- | --- | --- | --- |
| 0 | GP | | 12 | PTS |
| 3 | FGA | | 15 | REB |
| 4 | FGM | | 16 | AST |
| 5 | FG% | | 17 | ST |
| 6 | FTA | | 18 | BLK |
| 7 | FTM | | 19 | TO |
| 8 | FT% | | 10 | 3PTM |

Verified: LeBron `projected_stats` `4/3` = 463/907 = .510 = id `5`; `7/6` = 210/278 = .755 = id `8`.

**FGA/FGM and FTA/FTM are present**, so volume-weighted percentage z-scores are computable
without any external source — the plan flagged this as mandatory and it is already satisfied.

### `draftPicks` is two different keyings (2026-09-12)

`order` holds the pick objects themselves and `byId` is keyed by `playerId`, so
the two do not compose: `byId[order[i]]` stringifies the object to
`"[object Object]"` and misses on every pick. An adapter that assumed `order`
held keys silently reported a draft with zero picks — the board still computed,
it just computed round one forever, recommending players taken in round one.

Confirmed live at pick 71 of a 14-team mock:

    order sample: [{"id":"1","teamId":"1","playerId":"10094","cost":0}, ...]
    byId first:   3704 -> {"id":"49","teamId":"8","playerId":"3704","cost":0}

`extract()` now accepts either shape and emits a `picks-unmapped` status when
entries exist but none resolve, so the same failure cannot be silent twice.

## Recon questions answered

1. **URL pattern** — `/draftclient/nba/<draft_id>/<slot>`; mock and real share it, and
   `settings.is_mock_league` distinguishes them.
2. **Socket?** — Yes. `draftStatus.draftServer` + `draftPort: 443` is a dedicated draft host.
   Patching `fetch`/`WebSocket` *after* load captured nothing, because the connection is opened
   during page load. Interception therefore requires `run_at: "document_start"`. Moot anyway:
   `store.subscribe()` gives the same push semantics with none of the protocol risk.
3. **`__reactFiber$` resolves?** — Yes, on any `#app` descendant.
4. **Full pick list from before joining?** — Yes. `draftPicks` is server-rehydrated on load, so a
   refresh mid-draft loses nothing. This removes the plan's biggest fragility concern.
5. **Player ids?** — Yes, `id` and `player_key`. No fuzzy name matching needed.
6. **API needed for pool/settings/categories?** — No. `players`, `roster_positions` and
   `stat_categories` all come from the store, so no Yahoo API call is required during a draft.

## Consequences for the build

- `draftOrder.order` is the **complete** pick order, so "will he last until my next pick?" is
  computed against known pick numbers rather than estimated.
- ADP ships in the page — `tools/draft/adp.py` needs no external source.
- The `auction` slice means auction support is data-ready whenever it's wanted.
- The mock's clock is 30s (`pickTime: 30`); the real keeper league is 60s.
- `roster_positions` here is `PG, SG, G, SF, PF, F, C×2, Util×2, BN×3`; categories are standard
  9-cat.
- Yahoo's `projected_stats` have gaps — retired/inactive players project all zeros (e.g. Jeff
  Green, `inj: "NA"`). Any model consuming them must treat a zero line as missing, not as a
  projection of zero.
