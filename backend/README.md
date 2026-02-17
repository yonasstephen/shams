# Shams Backend API

FastAPI backend for Shams fantasy basketball analysis tool.

## Features

- Yahoo Fantasy Sports OAuth authentication
- Player search and statistics endpoints
- Waiver wire analysis with minute trends
- Matchup projections with category breakdowns
- Shared cache system with CLI (`~/.shams/`)

## API Endpoints

### Authentication

- `GET /api/auth/login` - Initiate Yahoo OAuth flow
- `GET /api/auth/callback` - OAuth callback handler
- `POST /api/auth/logout` - Logout current user
- `GET /api/auth/me` - Get current user info
- `GET /api/auth/leagues` - Get user's leagues

### Players

- `GET /api/players/search?name={name}` - Search for players
  - Parameters: `name` (string), `season_type` (optional, default: "Regular Season")
  - Returns: List of player suggestions or exact match
  
- `GET /api/players/{player_id}` - Get player statistics
  - Parameters: `season_type` (optional)
  - Returns: Comprehensive stats (last game, last3, last7, season)

### Waiver Wire

- `GET /api/waiver` - Get waiver wire players
  - Parameters:
    - `league_key` (required)
    - `count` (optional, default: 50)
    - `stats_mode` (optional, default: "last")
    - `agg_mode` (optional, default: "avg")
    - `sort_column` (optional)
    - `sort_ascending` (optional)
    - `refresh` (optional, default: false)
  - Returns: List of available players with stats and minute trends
  
- `POST /api/waiver/refresh?league_key={key}` - Force refresh waiver cache

### Matchup

- `GET /api/matchup` - Get matchup projection for user's team
  - Parameters: `league_key` (required), `week` (optional)
  - Returns: Current vs projected category totals, roster contributions
  
- `GET /api/matchup/all` - Get all league matchups
  - Parameters: `league_key` (required), `week` (optional)
  - Returns: All matchups in the league

## Development Setup

1. Install dependencies:
```bash
cd backend
pip install -r requirements.txt
```

2. Set environment variables:
```bash
export YAHOO_CONSUMER_KEY="your_key"
export YAHOO_CONSUMER_SECRET="your_secret"
export SESSION_SECRET="random_secret_key"
export FRONTEND_URL="http://localhost:5173"
```

3. Run the server:
```bash
uvicorn app.main:app --reload --port 8000
```

4. Access API docs at `http://localhost:8000/docs`

## Docker Development

```bash
# From project root
docker-compose up backend
```

## Production Deployment

1. Set production environment variables in `.env`
2. Build and run with production compose:
```bash
docker-compose -f docker-compose.prod.yml up -d
```

## Architecture

- **FastAPI** - Modern Python web framework
- **Pydantic** - Data validation and serialization
- **Yahoo Fantasy Sports API** - League and player data
- **NBA API** - Real-time NBA statistics
- **Shared Tools** - Reuses `tools/` module from CLI

## Cache System

The backend shares the cache directory (`~/.shams/`) with the CLI:
- Box scores and player game logs
- NBA team schedules
- Waiver player lists
- Yahoo OAuth tokens

This ensures fast performance and consistency across CLI and web interfaces.

