# Live draft assistant

Punt-aware 9-cat recommendations, category scarcity and standings impact, in a
Chrome side panel next to your Yahoo draft room.

- `docs/draft-room-recon.md` — how the Yahoo draft room is read, and what to do
  when that breaks.
- `extension/README.md` — installing and running the extension.

## What it tells you

At every pick, one headline recommendation with a single reason, three
alternatives, and behind tabs:

- **Scarcity** — elite sources left in each category versus teams that still
  need one, how many survive to *your* next pick (exact, because Yahoo publishes
  the whole draft order up front), and where the next tier cliff falls.
- **My team** — category standing against an average team, and every punt build
  tested by simulation.
- **Board** — the full pool with value above replacement, standings impact, ADP
  and survival probability.

## Draft-day checklist

```bash
# 1. Historical box scores (hours; resumable). Once per offseason.
pipenv run python scripts/backfill_seasons.py --seasons 4

# 2. Build the projection CSV. Minutes, not hours.
pipenv run python scripts/build_projections.py --season 2026-27

# 3. Review the numbers BEFORE draft day.
curl 'https://localhost:8000/api/draft/projections?season=2026-27&limit=50'

# 4. Fix anything wrong by hand — rookies, trades, role changes.
pipenv run python scripts/build_projections.py --season 2026-27 --template
$EDITOR ~/.shams/projections/2026-27.overrides.csv

# 5. Start the backend and confirm it answers.
./scripts/dev.sh
curl https://localhost:8000/api/draft/health

# 6. Load extension/ unpacked, open the draft room, open the side panel.
```

Step 3 matters more than it looks. The model is good on aggregate and wrong
about individuals, and the individuals are what you draft.

## Where the numbers come from

`ProjectionSource` has two implementations and the engine cannot tell them
apart:

| Source | Used when | Notes |
| --- | --- | --- |
| `shams-csv` | A CSV exists for the season | Our model, overrides applied |
| `yahoo` | No CSV, or a player is missing from it | Yahoo's own `projected_stats` |

Deleting the CSV is a valid mid-draft recovery: the assistant silently falls
back to Yahoo. The panel and the `/draft` page both show which source is live
and how many players it covered.

Yahoo's flag wins on availability regardless of source. A history-based model
happily projects a retired player — it has three seasons of his box scores and
no way to know he stopped playing — so anyone Yahoo marks `inj: "NA"` is left
out no matter what the CSV says.

## Is the model actually any good?

`tools/projections/backtest.py` is the gate, and the answer is recorded rather
than assumed. Predicting a held-out season, versus "last season repeated":

| Predicting | naive MAE | marcel | +residual | naive *r* | marcel | +residual |
| --- | --- | --- | --- | --- | --- | --- |
| 2025-26 | 0.930 | 0.864 | **0.841** | 0.785 | 0.789 | **0.798** |
| 2024-25 | 0.782 | 0.779 | **0.734** | 0.852 | 0.849 | **0.861** |

Marcel alone is a marginal improvement — clearly better on one season, a
rounding error on the other, and no better at *ranking*, which is the only thing
a draft needs. The residual correction is what makes the model worth using: it
wins on accuracy and ranking, on both seasons.

Reproduce:

```bash
pipenv run python -m tools.projections.backtest \
  --test 2025-26 --priors 2024-25 2023-24 \
  --residual --train 2024-25 --train-priors 2023-24 2022-23
```

**Draw priors from complete seasons only.** An incomplete backfill measurably
corrupts the model — including a season missing ~7% of its games was enough to
flip a result from a win to a loss.

## Known limits

- **Minutes are the weak point.** Games-played MAE is ~11 and MPG MAE ~4.
  Minutes dominate any fantasy projection and are the part statistics handles
  worst. Real improvement lives in depth charts and role news, not a fancier
  rate model.
- **Rookies are invisible to the model.** No NBA history, no projection. The
  ensemble fills them from external exports; the overrides file is the fallback.
- **The schedule adjustment is small on purpose** (±4%). Every team plays 82
  games, so only the weekly distribution survives, and a larger multiplier would
  be dressing up noise. Without a cached schedule the assistant runs
  schedule-neutral and says so.
- **Standings impact is quantized.** With 14 teams each category win is 1/13, so
  several candidates often show the same delta. It is honest, not broken.
- **One draft at a time.** `GET /api/draft/latest` is a single slot; two
  concurrent drafts would overwrite each other.

## Blending external projections

```bash
pipenv run python scripts/build_projections.py --season 2026-27 \
  --sources ~/Downloads/source-a.csv ~/Downloads/source-b.csv
```

Columns are resolved by alias, and season-totals files are detected and
converted (mistaking those for per-game is a factor-of-seventy error). Blending
is by median, not mean — sources disagree most about the players they are least
sure of, and one outlier would drag a mean badly.

Where the model and the consensus both have an opinion, **the model wins** — the
backtest is the evidence for it. External sources only fill players the model
cannot see. Disagreements are printed for review rather than averaged away.
