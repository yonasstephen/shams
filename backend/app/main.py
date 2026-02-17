"""Main FastAPI application."""

import logging
import os
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Add parent directory to path to import tools
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.api import auth, boxscore, config, league, matchup, players, refresh, waiver
from app.config import settings

# Configure logging - can be controlled via LOG_LEVEL environment variable
log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

app = FastAPI(title=settings.app_name, debug=settings.debug, version="1.0.0")

# Configure CORS
# In production (DEBUG=False), only allow configured frontend URL
# In development (DEBUG=True), also allow localhost URLs for local testing
allowed_origins = [settings.frontend_url]
if settings.debug:
    allowed_origins.extend(
        [
            "http://localhost:3000",
            "http://localhost:5173",
        ]
    )

# Remove any empty origins
allowed_origins = [origin for origin in allowed_origins if origin]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],  # Include OPTIONS for preflight
    allow_headers=[
        "Content-Type",
        "Cookie",
        "Authorization",
    ],  # Explicit list instead of wildcard
    expose_headers=["Set-Cookie"],  # Expose Set-Cookie header for credentials
)

# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(players.router, prefix="/api/players", tags=["players"])
app.include_router(waiver.router, prefix="/api/waiver", tags=["waiver"])
app.include_router(matchup.router, prefix="/api/matchup", tags=["matchup"])
app.include_router(config.router, prefix="/api/config", tags=["config"])
app.include_router(refresh.router, prefix="/api/refresh", tags=["refresh"])
app.include_router(league.router, prefix="/api/league", tags=["league"])
app.include_router(boxscore.router, prefix="/api/boxscore", tags=["boxscore"])


@app.get("/")
async def root():
    """Root endpoint."""
    return {"name": settings.app_name, "version": "1.0.0", "status": "running"}


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}
