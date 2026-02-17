# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Shams is a fantasy basketball analysis platform with two interfaces sharing the same core logic:
- **CLI** (`./shams`): Interactive shell using `prompt-toolkit` and `rich`
- **Web app**: React (TypeScript) frontend + FastAPI backend

Both interfaces import from the `tools/` module, which contains all core business logic.

## Commands

### CLI
```bash
pipenv install        # Install Python dependencies
pipenv run ./shams    # Run the interactive CLI
```

### Web App (Development)
```bash
./scripts/dev.sh      # Docker-based dev start (backend + frontend)

# Manual (without Docker):
cd backend && pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

cd frontend && npm install && npm run dev   # localhost:5173
```

### Testing
```bash
# Frontend
cd frontend && npm test
cd frontend && npm run test:coverage

# Backend - matchup projection tests (run before/after editing matchup logic)
cd tools/tests && pipenv run pytest test_matchup_projection.py -v

# Single test
cd tools/tests && pipenv run pytest test_matchup_projection.py::TestRosterContributionsVsProjections::test_player_added_after_game_started -v
```

### Linting & Type Checking
```bash
# Frontend (also type-checks)
cd frontend && npm run build

# Python
pipenv run pylint tools/
cd backend && pipenv run pylint app/
pipenv run pylint path/to/file.py   # single file
```

**Always run these after editing:** `.ts`/`.tsx` → `npm run build`; `.py` → `pipenv run pylint <file>`

## Architecture

### Shared Core (`tools/`)
All business logic lives here and is imported by both the CLI and the web backend:
- `tools/matchup/matchup_projection.py` — Complex matchup projection engine (88KB, critical file)
- `tools/boxscore/` — NBA box score fetching, caching, and player insights
- `tools/player/` — Player stats computation and minutes trends
- `tools/utils/yahoo.py` — Yahoo Fantasy Sports API wrapper with OAuth
- `tools/utils/player_index.py` — Yahoo ↔ NBA player ID mapping
- `tools/utils/stat_mappings.py` / `stat_thresholds.py` — Stat definitions and color thresholds

### CLI (`commands/`)
Each CLI command (e.g. `/player`, `/waiver`, `/matchup`) is a class in `commands/` that delegates to `tools/`.

### Web Backend (`backend/app/`)
FastAPI app with routers in `backend/app/api/` mirroring the CLI commands. Pydantic models in `backend/app/models/`.

### Frontend (`frontend/src/`)
- `pages/` — Page-level components (PlayerSearch, WaiverWire, Matchup, etc.)
- `components/` — Reusable UI components
- `context/` — React context for league, matchup, and waiver state
- `services/api.ts` — Axios HTTP client
- `utils/statColors.ts` — Color-coding logic mirroring Python thresholds

### Cache (`~/.shams/`)
JSON file-based persistent cache for NBA box scores, Yahoo league data, schedules, and OAuth tokens.

## Matchup Projection Logic (Critical)

When editing `tools/matchup/matchup_projection.py` or `backend/app/api/matchup.py`:

1. Run tests before and after: `cd tools/tests && pipenv run pytest test_matchup_projection.py -v`
2. Keep `current_player_contributions` (actual past stats) and `player_contributions` (future projections) **strictly separate**
3. Active players are those NOT in positions: `BN`, `IL`, `IL+`
4. Today's games: if a boxscore exists → classify as "current"; if not → classify as "remaining" (prevents double-counting)
5. Always update both user and opponent data symmetrically

## Configuration

Required `.env` variables:
```
YAHOO_CONSUMER_KEY=...
YAHOO_CONSUMER_SECRET=...
```

Optional: `SHAMS_YAHOO_TOKEN_DIR`, `WAIVER_BATCH_SIZE`, `NBA_API_TIMEOUT`, `NBA_API_REQUESTS_PER_SECOND`, and stat color threshold overrides (e.g. `STAT_PTS_GREEN_MIN`).
