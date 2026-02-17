"""Authentication API endpoints."""

import logging
import sys
from pathlib import Path
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from app.auth import yahoo_web
from app.config import settings

from tools.utils.yahoo import YahooAuthError, fetch_user_leagues

router = APIRouter()


class AuthCallbackRequest(BaseModel):
    """Request body for auth callback."""

    code: str
    state: str


@router.get("/init")
def init_session(response: Response):
    """Initialize session from existing tokens (shared with CLI) if available."""
    session_id = yahoo_web.get_or_create_session_from_tokens()

    if session_id:
        yahoo_web.set_session_cookie(response, session_id)
        return {
            "authenticated": True,
            "message": "Session restored from existing tokens",
        }

    return {"authenticated": False, "message": "No existing tokens found"}


@router.get("/login")
def login():
    """Initiate Yahoo OAuth flow."""
    if not settings.yahoo_consumer_key or not settings.yahoo_consumer_secret:
        raise HTTPException(
            status_code=500, detail="Yahoo OAuth credentials not configured"
        )

    # Generate state token for CSRF protection
    state = yahoo_web.generate_oauth_state()

    # Build Yahoo OAuth URL
    oauth_params = {
        "client_id": settings.yahoo_consumer_key,
        "redirect_uri": f"{settings.backend_url}/api/auth/callback",
        "response_type": "code",
        "state": state,
    }

    oauth_url = (
        f"https://api.login.yahoo.com/oauth2/request_auth?{urlencode(oauth_params)}"
    )

    return {"auth_url": oauth_url, "state": state}


def _get_yahoo_user_email(access_token: str) -> str:
    """Fetch the user's email from Yahoo API using access token."""
    import requests

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    # Yahoo Social API endpoint to get user profile
    profile_url = "https://social.yahooapis.com/v1/user/me/profile?format=json"

    try:
        response = requests.get(profile_url, headers=headers)
        response.raise_for_status()
        profile_data = response.json()

        # Extract email from profile
        emails = profile_data.get("profile", {}).get("emails", [])
        if emails:
            # Get primary email or first email
            for email_obj in emails:
                if email_obj.get("primary", False):
                    return email_obj.get("handle", "").lower()
            # If no primary, return first email
            return emails[0].get("handle", "").lower()

        raise ValueError("No email found in Yahoo profile")
    except Exception as e:
        logger.error("Failed to fetch Yahoo user email: %s", e)
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve user email: {str(e)}"
        )


@router.get("/callback")
def auth_callback(code: str, state: str, response: Response):
    """Handle Yahoo OAuth callback."""
    # Validate state token
    if not yahoo_web.validate_oauth_state(state):
        raise HTTPException(status_code=400, detail="Invalid state token")

    # Exchange code for access token using Yahoo OAuth2
    import requests

    token_url = "https://api.login.yahoo.com/oauth2/get_token"

    token_data = {
        "client_id": settings.yahoo_consumer_key,
        "client_secret": settings.yahoo_consumer_secret,
        "redirect_uri": f"{settings.backend_url}/api/auth/callback",
        "code": code,
        "grant_type": "authorization_code",
    }

    try:
        token_response = requests.post(token_url, data=token_data)
        token_response.raise_for_status()
        tokens = token_response.json()

        # Check email whitelist if configured
        if settings.allowed_yahoo_emails:
            user_email = _get_yahoo_user_email(tokens.get("access_token"))

            if user_email not in settings.allowed_yahoo_emails:
                logger.warning("Unauthorized email attempted login: %s", user_email)
                raise HTTPException(
                    status_code=403,
                    detail="Access denied. Your Yahoo account is not authorized to use this application.",
                )

        # Create session with tokens
        session_id = yahoo_web.create_session(
            {
                "oauth_code": code,
                "authenticated": True,
                "access_token": tokens.get("access_token"),
                "refresh_token": tokens.get("refresh_token"),
                "expires_in": tokens.get("expires_in"),
            }
        )

        # Store tokens for yfpy
        yahoo_web.save_yahoo_tokens(session_id, tokens)

    except HTTPException:
        # Re-raise HTTPExceptions (including 403 from email check)
        raise
    except Exception as e:
        logger.exception("Token exchange failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Token exchange failed: {str(e)}")

    # Set session cookie and redirect
    # Note: We need to create the redirect response first, then set cookie on it
    redirect_response = RedirectResponse(url=f"{settings.frontend_url}/auth/success")
    yahoo_web.set_session_cookie(redirect_response, session_id)
    return redirect_response


@router.post("/logout")
def logout(request: Request, response: Response):
    """Logout current user."""
    session_cookie = request.cookies.get("session")
    if session_cookie:
        try:
            from itsdangerous import URLSafeTimedSerializer

            serializer = URLSafeTimedSerializer(settings.secret_key)
            session_id = serializer.loads(session_cookie, max_age=86400 * 7)
            yahoo_web.delete_session(session_id)
        except Exception:
            pass

    response.delete_cookie("session")
    return {"message": "Logged out successfully"}


@router.get("/me")
def get_current_user(request: Request):
    """Get current user info."""
    session = yahoo_web.get_session_from_request(request)

    # Try to fetch user's leagues to verify authentication
    try:
        leagues = fetch_user_leagues()
        return {"authenticated": True, "leagues": leagues}
    except YahooAuthError as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")
    except Exception as e:
        logger.error("Unexpected error in /me: %s", e)
        raise HTTPException(
            status_code=500, detail=f"Failed to verify authentication: {str(e)}"
        )


@router.get("/leagues")
def get_user_leagues(request: Request):
    """Get user's Yahoo Fantasy leagues."""
    session_id = None
    try:
        # Get session ID from cookie for potential cleanup
        session_cookie = request.cookies.get("session")
        if session_cookie:
            try:
                session_id = yahoo_web.serializer.loads(session_cookie, max_age=86400 * 30)
            except Exception:
                pass
        session = yahoo_web.get_session_from_request(request)
    except HTTPException as e:
        # Re-raise auth errors (401) directly
        raise

    try:
        leagues = fetch_user_leagues()
        return {"leagues": leagues}
    except YahooAuthError:
        # Yahoo authentication failed - token expired or invalid
        # Clear the session to force re-authentication
        if session_id:
            yahoo_web.delete_session(session_id)
        raise HTTPException(
            status_code=401, detail="Authentication expired. Please log in again."
        )
    except Exception as e:
        error_msg = str(e).lower()
        # Check if this is an authentication error
        if any(
            keyword in error_msg
            for keyword in ["token_expired", "oauth", "unauthorized", "authentication"]
        ):
            raise HTTPException(
                status_code=401, detail="Authentication expired. Please log in again."
            )
        logger.exception("Failed to fetch leagues: %s", e)
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch leagues: {str(e)}"
        )
