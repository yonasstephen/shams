"""Yahoo OAuth authentication for web."""

import json
import logging
import secrets
import sys
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

from fastapi import HTTPException, Request, Response
from itsdangerous import URLSafeTimedSerializer

# Add tools to path for shared utilities
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.config import settings

# Session storage file
SESSION_FILE = settings.yahoo_token_dir / "sessions.json"
OAUTH_STATES_FILE = settings.yahoo_token_dir / "oauth_states.json"

# In-memory session storage (synced with disk)
_sessions: dict[str, dict] = {}
_oauth_states: dict[str, float] = {}  # state -> timestamp

# Token serializer for secure cookies
serializer = URLSafeTimedSerializer(settings.secret_key)


# Encryption removed - tokens stored as plain text in ~/.shams/yahoo/
# Directory is already protected by filesystem permissions


def _load_tokens_from_env_file() -> Optional[dict]:
    """Load Yahoo tokens from yfpy's .env file (shared with CLI)."""
    env_file = settings.yahoo_token_dir / ".env"
    if not env_file.exists():
        return None

    try:
        tokens = {}
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, value = line.split("=", 1)
                    # Remove quotes from value
                    value = value.strip('"').strip("'")

                    # Map env var names to token keys
                    if key == "YAHOO_ACCESS_TOKEN":
                        tokens["access_token"] = value
                    elif key == "YAHOO_REFRESH_TOKEN":
                        tokens["refresh_token"] = value
                    elif key == "YAHOO_TOKEN_TYPE":
                        tokens["token_type"] = value
                    elif key == "YAHOO_TOKEN_EXPIRES_IN":
                        try:
                            tokens["expires_in"] = int(value)
                        except ValueError:
                            tokens["expires_in"] = 3600
                    elif key == "YAHOO_TOKEN_CREATED_AT":
                        try:
                            tokens["token_created_at"] = float(value)
                        except ValueError:
                            # If parsing fails, omit it (will be treated as expired)
                            pass

        if tokens.get("access_token") and tokens.get("refresh_token"):
            return tokens
    except Exception as e:
        logger.warning("Failed to load tokens from .env file: %s", e)

    return None


def _cleanup_expired_sessions() -> None:
    """Remove expired sessions from memory and disk."""
    global _sessions

    expired_sessions = []
    current_time = time.time()

    for session_id, session_data in list(_sessions.items()):
        # Check both yahoo_tokens and user_data for expiry
        tokens = session_data.get("yahoo_tokens") or session_data.get("user_data", {})

        if not tokens:
            expired_sessions.append(session_id)
            continue

        token_created_at = tokens.get("token_created_at")
        expires_in = tokens.get("expires_in")

        # If missing required fields, consider expired
        if not token_created_at or not expires_in:
            expired_sessions.append(session_id)
            continue

        try:
            expiry_time = float(token_created_at) + int(expires_in)
            # Consider expired if past expiry time (no buffer here, just cleanup)
            if current_time > expiry_time:
                expired_sessions.append(session_id)
        except (ValueError, TypeError):
            expired_sessions.append(session_id)

    # Remove expired sessions
    for session_id in expired_sessions:
        _sessions.pop(session_id, None)

    if expired_sessions:
        _save_sessions_to_disk()
        logger.debug("Cleaned up %d expired session(s)", len(expired_sessions))


def _load_sessions_from_disk() -> None:
    """Load sessions from disk on startup."""
    global _sessions

    # First, try to load existing sessions
    if SESSION_FILE.exists():
        try:
            with open(SESSION_FILE, "r", encoding="utf-8") as f:
                _sessions = json.load(f)

        except Exception as e:
            logger.warning("Failed to load sessions from disk: %s", e)
            _sessions = {}
    else:
        _sessions = {}

    # If no sessions exist, try to load tokens from yfpy's .env file (shared with CLI)
    if not _sessions:
        tokens = _load_tokens_from_env_file()
        if tokens:
            # Create a session with these tokens
            session_id = secrets.token_urlsafe(32)
            _sessions[session_id] = {
                "user_data": {
                    "authenticated": True,
                    "access_token": tokens.get("access_token"),
                    "refresh_token": tokens.get("refresh_token"),
                    "expires_in": tokens.get("expires_in", 3600),
                    "token_type": tokens.get("token_type", "bearer"),
                    "token_created_at": time.time()
                    - 3500,  # Assume token is old, will refresh if needed
                },
                "yahoo_tokens": tokens,
            }
            _save_sessions_to_disk()

    # Clean up any expired sessions
    _cleanup_expired_sessions()


def _save_sessions_to_disk() -> None:
    """Save sessions to disk."""
    try:
        SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)

        with open(SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump(_sessions, f, indent=2)
    except Exception as e:
        logger.error("Failed to save sessions to disk: %s", e)


# Load sessions on module import
_load_sessions_from_disk()


def get_or_create_session_from_tokens() -> Optional[str]:
    """Get existing session or create one from .env tokens if available.

    Returns session_id if a session exists or can be created, None otherwise.
    """
    # If we already have sessions, return the one with the newest tokens
    # (In a multi-user app, you'd need better session management)
    if _sessions:
        # Find the session with the most recent token_created_at
        newest_session_id = None
        newest_timestamp = 0

        for session_id, session_data in _sessions.items():
            # Check both yahoo_tokens and user_data for token_created_at
            tokens = session_data.get("yahoo_tokens") or session_data.get("user_data", {})
            token_created_at = tokens.get("token_created_at", 0)

            if token_created_at and token_created_at > newest_timestamp:
                newest_timestamp = token_created_at
                newest_session_id = session_id

        if newest_session_id:
            return newest_session_id

        # Fallback to first session if no timestamps found
        return next(iter(_sessions.keys()))

    # Try to create a session from .env tokens
    tokens = _load_tokens_from_env_file()
    if tokens:
        session_id = secrets.token_urlsafe(32)
        _sessions[session_id] = {
            "user_data": {
                "authenticated": True,
                "access_token": tokens.get("access_token"),
                "refresh_token": tokens.get("refresh_token"),
                "expires_in": tokens.get("expires_in", 3600),
                "token_type": tokens.get("token_type", "bearer"),
                "token_created_at": time.time()
                - 3500,  # Assume token is old, will refresh if needed
            },
            "yahoo_tokens": tokens,
        }
        _save_sessions_to_disk()
        return session_id

    return None


def _load_oauth_states_from_disk() -> None:
    """Load OAuth states from disk."""
    global _oauth_states

    if OAUTH_STATES_FILE.exists():
        try:
            with open(OAUTH_STATES_FILE, "r", encoding="utf-8") as f:
                _oauth_states = json.load(f)
            # Clean up expired states (older than 10 minutes)
            current_time = time.time()
            _oauth_states = {
                state: timestamp
                for state, timestamp in _oauth_states.items()
                if current_time - timestamp < 600  # 10 minutes
            }
            _save_oauth_states_to_disk()
        except Exception as e:
            logger.warning("Failed to load OAuth states from disk: %s", e)
            _oauth_states = {}
    else:
        _oauth_states = {}


def _save_oauth_states_to_disk() -> None:
    """Save OAuth states to disk."""
    try:
        OAUTH_STATES_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(OAUTH_STATES_FILE, "w", encoding="utf-8") as f:
            json.dump(_oauth_states, f)
    except Exception as e:
        logger.error("Failed to save OAuth states to disk: %s", e)


def generate_oauth_state() -> str:
    """Generate a secure random state token for OAuth."""
    # Reload states from disk to get latest (for multi-worker support)
    _load_oauth_states_from_disk()
    state = secrets.token_urlsafe(32)
    _oauth_states[state] = time.time()
    _save_oauth_states_to_disk()
    return state


def validate_oauth_state(state: str) -> bool:
    """Validate OAuth state token."""
    # Reload states from disk to get latest (for multi-worker support)
    _load_oauth_states_from_disk()
    if state in _oauth_states:
        del _oauth_states[state]
        _save_oauth_states_to_disk()
        return True
    return False


def create_session(user_data: dict) -> str:
    """Create a new session and return session ID."""
    session_id = secrets.token_urlsafe(32)

    # Store token creation timestamp for expiry checking
    if "expires_in" in user_data:
        user_data["token_created_at"] = time.time()

    _sessions[session_id] = {"user_data": user_data, "yahoo_tokens": {}}
    _save_sessions_to_disk()
    return session_id


def get_session(session_id: Optional[str]) -> Optional[dict]:
    """Get session data by ID."""
    if not session_id:
        return None
    return _sessions.get(session_id)


def update_session_tokens(session_id: str, tokens: dict) -> None:
    """Update Yahoo tokens in session."""
    if session_id in _sessions:
        tokens["token_created_at"] = time.time()
        _sessions[session_id]["yahoo_tokens"] = tokens
        _save_sessions_to_disk()


def delete_session(session_id: str) -> None:
    """Delete a session."""
    _sessions.pop(session_id, None)
    _save_sessions_to_disk()


def _is_token_expired(tokens: dict) -> bool:
    """Check if access token is expired."""
    if not tokens:
        return True

    # If token_created_at is missing or None, we can't determine expiry reliably
    # Treat as potentially expired to force a refresh attempt
    if "token_created_at" not in tokens or tokens["token_created_at"] is None:
        return True

    if "expires_in" not in tokens:
        return True

    try:
        created_at = float(tokens["token_created_at"])
        expires_in = int(tokens["expires_in"])
        current_time = time.time()
        expiry_time = created_at + expires_in - 300  # 5 minute buffer

        is_expired = current_time >= expiry_time

        # Consider token expired 5 minutes before actual expiry for safety
        return is_expired
    except (ValueError, TypeError):
        return True


def _refresh_access_token(session_id: str, refresh_token: str) -> dict:
    """Refresh the access token using the refresh token."""
    import requests

    token_url = "https://api.login.yahoo.com/oauth2/get_token"
    token_data = {
        "client_id": settings.yahoo_consumer_key,
        "client_secret": settings.yahoo_consumer_secret,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }

    try:
        response = requests.post(token_url, data=token_data, timeout=30)
        response.raise_for_status()
        new_tokens = response.json()

        # Preserve refresh_token if not returned in response (Yahoo sometimes doesn't return it)
        if "refresh_token" not in new_tokens:
            new_tokens["refresh_token"] = refresh_token

        # Update session with new tokens
        update_session_tokens(session_id, new_tokens)

        # Save to yfpy storage (this also clears the query cache)
        save_yahoo_tokens(session_id, new_tokens)

        return new_tokens
    except Exception as e:
        logger.error("Failed to refresh token: %s", e)
        raise HTTPException(
            status_code=401, detail=f"Failed to refresh token: {str(e)}"
        ) from e


def get_session_from_request(request: Request) -> dict:
    """Extract and validate session from request."""
    session_cookie = request.cookies.get("session")

    if not session_cookie:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        session_id = serializer.loads(session_cookie, max_age=86400 * 30)  # 30 days
    except Exception as e:
        logger.warning("Failed to decode session cookie: %s", e)
        raise HTTPException(status_code=401, detail="Invalid session") from e

    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="Session expired")

    # Check if token needs refreshing
    # Prefer yahoo_tokens (set by token refresh), fallback to user_data (set on initial login)
    tokens = (
        session.get("yahoo_tokens")
        if session.get("yahoo_tokens")
        else session.get("user_data", {})
    )

    if _is_token_expired(tokens):
        refresh_token = tokens.get("refresh_token")
        if refresh_token:
            # _refresh_access_token handles updating session and saving to disk
            _refresh_access_token(session_id, refresh_token)
        else:
            raise HTTPException(
                status_code=401, detail="Token expired and cannot be refreshed"
            )

    return session


def save_yahoo_tokens(session_id: str, tokens: dict) -> None:
    """Save Yahoo OAuth tokens to yfpy's token storage and session."""
    # Update session
    update_session_tokens(session_id, tokens)

    # Also save to yfpy's expected location (~/.shams/yahoo/.env)
    token_dir = settings.yahoo_token_dir
    token_dir.mkdir(parents=True, exist_ok=True)
    env_file = token_dir / ".env"

    # Write tokens in plain text (directory protected by filesystem permissions)
    # Use atomic write to prevent file corruption from concurrent writes
    token_created_at = tokens.get("token_created_at", time.time())

    from tools.utils.file_utils import write_env_file

    env_vars = {
        "YAHOO_ACCESS_TOKEN": tokens.get("access_token", ""),
        "YAHOO_REFRESH_TOKEN": tokens.get("refresh_token", ""),
        "YAHOO_TOKEN_TYPE": tokens.get("token_type", "bearer"),
        "YAHOO_TOKEN_EXPIRES_IN": str(tokens.get("expires_in", 3600)),
        "YAHOO_TOKEN_CREATED_AT": str(token_created_at),
    }
    write_env_file(env_file, env_vars)

    # Clear the yfpy query cache to force recreation with new tokens
    try:
        # Add project root to path (parent.parent.parent.parent goes from backend/app/auth/ to project root)
        project_root = Path(__file__).parent.parent.parent.parent
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))
        from tools.utils.yahoo import clear_query_cache

        clear_query_cache()
    except Exception as e:
        logger.exception("Failed to clear yfpy query cache: %s", e)


def set_session_cookie(response: Response, session_id: str) -> None:
    """Set session cookie on response.

    Uses environment-based configuration:
    - COOKIE_SECURE=true: secure=True, samesite="strict" (production with HTTPS)
    - COOKIE_SECURE=false: secure=False, samesite="lax" (local development)
    """
    session_token = serializer.dumps(session_id)

    # Use environment-based cookie security settings
    # Production (HTTPS): secure=True, samesite="strict"
    # Development (HTTP): secure=False, samesite="lax"
    response.set_cookie(
        key="session",
        value=session_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict" if settings.cookie_secure else "lax",
        max_age=86400 * 30,  # 30 days (tokens auto-refresh)
        path="/",
    )
