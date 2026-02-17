# Shams Fantasy Basketball

Fantasy basketball analysis platform with two interfaces sharing the same core logic:

- **CLI** (`./shams`) — Interactive terminal shell for player stats, waiver analysis, and matchup projections
- **Web app** — React frontend + FastAPI backend with the same features in a modern UI

> **Getting started?** See [QUICKSTART.md](QUICKSTART.md) for CLI, web app, and production setup.

## Features

- **Player Search** — Stats across multiple periods: last game, last 3/7 games, season average
- **Waiver Wire** — Browse free agents with 9-category stats, minute trends, and sorting
- **Matchup Projection** — Current head-to-head scoreboard with projected category outcomes
- **All League Matchups** — Projections for every matchup in the league
- **Box Scores** — Daily NBA box scores with player stats and game results
- **Color-coded Stats** — Green/yellow/white/red thresholds configurable per league scoring system
- **Shared Cache** — CLI and web app share `~/.shams/` — refresh in one, both benefit

## CLI Commands

Run the interactive shell:

```bash
pipenv run ./shams
```

### `/player <name> [--season-type <segment>]`

Display comprehensive player statistics across multiple time periods (last game, last 3, last 7, season). Shows all 9-category fantasy stats plus minutes.

Season segments: `Regular Season`, `Playoffs`, `Pre Season`, `All Star` (default: Regular Season)

If the name is ambiguous, the CLI lists up to 50 matches — reply with a number to select.

### `/waiver [<league_key>] [-r] [-c COUNT] [-s MODE] [--sort COLUMN]`

Fetch Yahoo Fantasy free agents and waiver wire players with stats and minute trends.

Flags:
- `-r` — Refresh the player cache from Yahoo API
- `-c COUNT` — Number of players to display (default: 25)
- `-s MODE` — Stats aggregation: `last` (most recent game), `last<N>` (average over N games, e.g. `last7`), `season`
- `--sort COLUMN` — Sort by: `FG%`, `FT%`, `3PM`, `PTS`, `REB`, `AST`, `STL`, `BLK`, `TO`, `MIN TREND`, `MINUTE`

Columns:
- **Min Trend** — Change in minutes from previous 3-game average (positive = increasing role)
- **Minute** — Average minutes based on selected mode

On first use, Yahoo OAuth opens a browser window for login, then prompts for the verification code. Refresh tokens are stored at `~/.shams/yahoo/` for subsequent runs.

Examples:
```
/waiver -c 10
/waiver -s last7 --sort PTS
/waiver -s season -c 15
```

### `/set-league [<league_key>]`

Store a default Yahoo league key. Subsequent Yahoo-backed commands use this selection automatically.

### `/matchup [<league_key>]`

Display the current head-to-head scoreboard and projected end-of-week category totals. Shows `current / projected` values with a color-coded margin column.

### `/matchup-all [<league_key>]`

Projections for every matchup in the league. **Requires running `/refresh` at least once** to populate the NBA schedule cache.

### `/refresh [-s START_DATE] [-e END_DATE]`

Refresh all cached data: box scores, season stats, NBA schedules, and waiver player lists. Defaults to season start (Oct 21) through today.

### Example session

```
$ ./shams
shams: /player LeBron James

Player Stats: LeBron James (ID 2544)
┏━━━━━━━━━━━┳━━━━━━━┳━━━━━━━┳━━━━━┳━━━━━┳━━━━━┳━━━━━┳━━━━━┳━━━━━┳━━━━━┳━━━━━━┓
┃ Period    ┃  FG%  ┃  FT%  ┃ 3PM ┃ PTS ┃ REB ┃ AST ┃ STL ┃ BLK ┃  TO ┃ MIN  ┃
┡━━━━━━━━━━━╇━━━━━━━╇━━━━━━━╇━━━━━╇━━━━━╇━━━━━╇━━━━━╇━━━━━╇━━━━━╇━━━━━╇━━━━━━┩
│ Last Game │ 52.4% │ 75.0% │ 2.0 │28.0 │ 8.0 │11.0 │ 1.0 │ 1.0 │ 3.0 │ 36.5 │
│ Last 3    │ 48.2% │ 80.0% │ 2.3 │25.7 │ 7.3 │ 9.7 │ 1.3 │ 0.7 │ 2.7 │ 35.2 │
│ Last 7    │ 50.1% │ 78.5% │ 2.1 │26.4 │ 7.9 │10.1 │ 1.1 │ 0.9 │ 3.1 │ 34.8 │
│ Season    │ 49.8% │ 77.2% │ 2.0 │25.8 │ 7.5 │ 9.8 │ 1.2 │ 0.8 │ 3.0 │ 35.1 │
└───────────┴───────┴───────┴─────┴─────┴─────┴─────┴─────┴─────┴─────┴──────┘
Minute Trend: +1.4 (↑ trending up from 3-game average)
```

## Configuration

All settings via `.env` (copy from `.env.example`):

### Required

```env
YAHOO_CONSUMER_KEY=your_consumer_key_here
YAHOO_CONSUMER_SECRET=your_consumer_secret_here
```

Get credentials from [Yahoo Developer Network](https://developer.yahoo.com/apps/).

### Optional

| Variable | Default | Description |
|---|---|---|
| `SHAMS_YAHOO_TOKEN_DIR` | `~/.shams/yahoo` | Directory for Yahoo OAuth tokens |
| `WAIVER_BATCH_SIZE` | `50` | Waiver players fetched per batch |
| `NBA_API_TIMEOUT` | `60` | NBA API request timeout (seconds) |
| `NBA_API_REQUESTS_PER_SECOND` | `2.0` | NBA API rate limit (lower = more conservative) |
| `SESSION_SECRET` | — | Required for web app; generate with `openssl rand -hex 32` |
| `ALLOWED_YAHOO_EMAILS` | — | Comma-separated whitelist; empty = allow all Yahoo accounts |
| `COOKIE_SECURE` | `false` | Set `true` in production (requires HTTPS) |
| `BACKEND_URL` | — | Public backend URL for web app OAuth redirect |
| `FRONTEND_URL` | — | Public frontend URL for CORS |
| `DEBUG` | `True` | Set `False` in production |

### Stat Color Thresholds

Customize the color coding to match your league's scoring system or punt strategy.

Colors: green (excellent) → yellow (solid) → white (low) → red (negative/bad %)

```env
# Punt-assists strategy
STAT_AST_YELLOW_MIN=2
STAT_AST_GREEN_MIN=4

# Points-heavy league
STAT_PTS_YELLOW_MIN=8
STAT_PTS_GREEN_MIN=18
```

| Stat | Variables | Defaults |
|------|-----------|----------|
| PTS | `STAT_PTS_YELLOW_MIN`, `STAT_PTS_GREEN_MIN` | 5, 13 |
| REB | `STAT_REB_YELLOW_MIN`, `STAT_REB_GREEN_MIN` | 5, 9 |
| AST | `STAT_AST_YELLOW_MIN`, `STAT_AST_GREEN_MIN` | 3, 6 |
| 3PM | `STAT_3PM_YELLOW_MIN`, `STAT_3PM_GREEN_MIN` | 2, 4 |
| STL | `STAT_STL_YELLOW_MIN`, `STAT_STL_GREEN_MIN` | 2, 3 |
| BLK | `STAT_BLK_YELLOW_MIN`, `STAT_BLK_GREEN_MIN` | 2, 3 |
| TO | `STAT_TO_GREEN_MAX`, `STAT_TO_YELLOW_MAX` | 2, 4 (inverse) |
| FG% | `STAT_FG_PCT_RED_MAX`, `STAT_FG_PCT_YELLOW_MAX` | 0.30, 0.50 |
| FT% | `STAT_FT_PCT_RED_MAX`, `STAT_FT_PCT_YELLOW_MAX` | 0.60, 0.80 |
| USG% | `STAT_USG_PCT_YELLOW_MIN`, `STAT_USG_PCT_GREEN_MIN` | 0.15, 0.25 |
| MIN | `STAT_MIN_YELLOW_MIN`, `STAT_MIN_GREEN_MIN` | 10, 18 |

## Cache

All data is stored under `~/.shams/`:

```
~/.shams/
├── config.json              # Default league (set via /set-league)
├── history                  # CLI command history
├── player_index.json        # Yahoo ↔ NBA player ID mappings
├── yahoo/                   # OAuth tokens and API cache
├── waiver/                  # Per-league free agent cache
│   └── {league_key}.json
├── rankings/                # Per-league Yahoo player rankings
│   └── {league_key}.json
├── league/                  # League settings cached from Yahoo
│   ├── {league_key}_weeks.json
│   └── {league_key}_roster.json
├── boxscores/               # NBA game data and player logs
│   ├── games/{season}/
│   ├── players/
│   └── season_stats/{season}/
└── nba_schedules/           # Team schedules and player-team index
    ├── schedules/{season}/
    ├── player_index/{season}/
    └── full_schedule_{season}.json
```

The CLI and web app share this directory — refreshing in one updates both.

## Testing

```bash
# Frontend (unit + integration)
cd frontend && npm test
cd frontend && npm run test:coverage

# Backend (unit tests only; integration tests require live API credentials)
pipenv run pytest tools/tests/ -v -m "not integration and not slow"
```

## Linting

```bash
# Frontend (also type-checks via tsc)
cd frontend && npm run build

# Python
./scripts/lint.sh
# or single file: pipenv run pylint path/to/file.py
```

## Troubleshooting

**CLI: `ModuleNotFoundError: No module named 'nba_api'`**
Run `pipenv install` from the project root.

**CLI: Slow `/waiver`**
The first run builds the box score cache (~2-3 min). Subsequent runs are fast.

**CLI: `/matchup-all` timeout or "Box score cache is empty"**
Run `/refresh` first to populate the NBA schedule cache.

**Web app: 401 Unauthorized**
Click "Login with Yahoo" to authenticate.

**Web app: CORS errors**
Ensure `FRONTEND_URL` and `BACKEND_URL` match your deployment URLs exactly.

**Web app: "Failed to load leagues"**
Backend isn't reachable from the frontend — check port 8000 is running and `BACKEND_URL` is correct.

**Docker (macOS): "Cannot connect to Docker daemon"**
Run `colima start`.

For setup and deployment issues, see [QUICKSTART.md](QUICKSTART.md).

## License

This project uses the [MIT License](LICENSE).
