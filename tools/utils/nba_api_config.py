"""Configuration for NBA API settings."""

from __future__ import annotations

import os

# Configure NBA API timeout globally
# The nba_api library uses requests under the hood
# We'll monkey-patch the timeout setting


def configure_nba_api_timeout(timeout: int = 60) -> None:
    """Configure the NBA API with a custom timeout.

    Args:
        timeout: Timeout in seconds (default: 60)
    """
    try:
        from nba_api.stats.library import http

        # Store original request method
        original_request = http.NBAStatsHTTP.send_api_request

        # Create wrapper with timeout
        def request_with_timeout(self, *args, **kwargs):
            """Wrapper that adds timeout to NBA API requests."""
            kwargs["timeout"] = timeout
            return original_request(self, *args, **kwargs)

        # Monkey-patch the request method
        http.NBAStatsHTTP.send_api_request = request_with_timeout

    except (ImportError, AttributeError):
        # If nba_api structure changes, fail silently
        pass


# Configure on import; default 15s — if NBA API doesn't respond in 15s it won't at all
_timeout = int(os.getenv("NBA_API_TIMEOUT", "15"))
configure_nba_api_timeout(timeout=_timeout)
