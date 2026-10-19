# Trade insights

Yahoo Fantasy Plus sells a Trade Hub: team strengths and weaknesses, a league-wide strength
grid, three suggested trade partners, and position ranks on the players being shopped.
`docs/season-page-recon.md` records how it works. This is the Shams version, built into the
season extension (`extension-season/`) so it runs without a server.

## Why not copy Yahoo

Yahoo measures everything **by roster slot**. That is a football model. In a head-to-head
categories league a slot is a poor proxy: a team that ranks last at C can still lead the
league in rebounds and blocks through its power forwards, and what decides a trade is which
categories it moves. Yahoo's analysis also ignores punts, schedule and FG%/FT% volume.

So Shams answers the same questions in categories, using the league's own scoring settings:

| Yahoo | Shams |
| --- | --- |
| Strengths / Neutral / Weaknesses by slot | the same three buckets, by category, with each team's league rank |
| League roster grid by slot | team × category rank grid; slots as a secondary toggle |
| Needs: weakest slots | weakest categories, same rule (weak first, padded with neutral) |
| Top 3 partners: complementary slots | partners whose surpluses cover your needs *and* vice versa |
| "Create a trade" | concrete trades where both sides gain expected category wins |
| Current / projected position rank | Shams value and position rank from the same model |

## The model

**Player lines.** Rest of season, each player's per-game line is the preseason projection
blended with season-to-date: `w = gp / (gp + 25)` on the season sample. The prior's weight
borrows `REGRESSION_GAMES` from `tools/projections/marcel.py`; it has not been backtested for
this use yet (see open questions). Players with no projection blend against last season. The
existing projection windows (season, last 30 days, …) can be chosen instead.

**Player value.** Per-category z-scores ported from `tools/draft/value_model.py`, with FG% and
FT% scored as makes above a league-average shooter on the same attempts, and turnovers
inverted. The reference pool is every player rostered in the league. The TypeScript is held
to the Python by a parity fixture.

**Team strength.** Each team plays out the rest of the season day by day: on every date, its
healthy players with a game fill the league's active slots, best value first, re-optimized
daily (a value-greedy matching, which is optimal for slot assignment). Starters' lines are
summed with percentages pooled from makes and attempts, and divided into weekly figures.
Players in IL slots are left out.

**Profile.** For each category, a team's rank in the league and its *win share*: the share of
other teams it beats on those weekly totals. Ranks split into thirds: strong, neutral, weak.
The sum of win shares is the team's expected categories won against a random league
opponent, the single number the league grid sorts on. Slot strength is the same exercise
with the value each slot's starters produce, measured above the league's worst rostered
player: raw z is centred on the average rostered player, so without that shift an empty slot
would outrank one filled by a below-average starter.

## Where it shows

A Shams panel at the top of the Trade Hub page, above Yahoo's own sections, which are left
alone (locks and upsells included). The panel is inserted outside Yahoo's React root.

## Phases

1. **Profile and grid.** Valuation port and parity fixture, league rosters, team profile for
   any team, league grid with a slot toggle.
2. **Partners and rows.** Trade partners; Shams chips on Yahoo's trading-block and
   most-traded rows (value, position ranks, owner's needs, fit for you); punt selection per
   league; the team profile on every team page.
3. **Trades.** Search 1-for-1 and 2-for-2 swaps with the top partners and keep those where
   both sides gain; then a trade evaluator on Yahoo's propose-trade page (needs DOM recon).

## Decisions

- **Categories first, slots second.** The point of building this rather than paying for Plus.
- **TypeScript first.** Like `engine/adds.ts`, only the valuation is a port; the rest has no
  Python counterpart yet. Move it into `tools/` if the web app needs it after Yahoo's API
  approval.
- **No Yahoo Plus data.** The extension never requests the gated fields.
- **After `trade_end_date`** the profile still renders, flagged as past the deadline.

## Open questions

- **Blend weight.** Backtest `gp / (gp + K)` against last season: build a feed anchored at,
  say, 1 December (`scripts/build_feed.py 2025-26 --today 2025-12-01`), predict rest-of-season
  per-game lines, and compare with what happened.
- **IL stashes.** A star on IL for two weeks is excluded entirely, which undersells a team.
  Return dates are not in the feed.
- **Fantasy playoffs.** Weeks from `playoff_start_week` could be weighted more, since that is
  where trades pay off.
