"""Tests for classifying a Yahoo error as a dead credential.

The wrapper only refreshes tokens for errors it recognises as auth failures.
Recognising too few sends a rejected token back to the caller as a 500; too
many sends unrelated failures through a pointless refresh and reports them as
a logout. Both matter, so both are pinned here.
"""

from __future__ import annotations

import pytest
from yfpy.exceptions import YahooFantasySportsException

from tools.utils import yahoo


@pytest.mark.parametrize(
    "message",
    [
        # Observed in the wild from a 20-day-old token, and the reason this
        # classifier was widened: it previously fell through as a raw error.
        'Attempt to retrieve data at URL https://fantasysports.yahooapis.com/'
        'fantasy/v2/users;use_login=1/games;game_keys=nba/leagues/?format=json '
        'failed with error: "This application is not authorized to perform this action."',
        "oauth_problem=token_expired",
        "token_expired",
        "invalid_token",
        "invalid_grant",
        "401 Unauthorized",
    ],
)
def test_auth_failures_are_recognised(message):
    assert yahoo._is_auth_error(message) is True


@pytest.mark.parametrize(
    "message",
    [
        # A player key containing "401" must not read as an HTTP 401 — yfpy
        # embeds the request URL in the message, so this is a real payload.
        'Attempt to retrieve data at URL https://fantasysports.yahooapis.com/'
        'fantasy/v2/league/466.l.38841/players;player_keys=466.p.4012/stats '
        'failed with error: "Player key does not exist."',
        "Attempt to retrieve data failed with error: \"League does not exist.\"",
        "Connection aborted, RemoteDisconnected",
        "",
    ],
)
def test_other_failures_are_left_alone(message):
    assert yahoo._is_auth_error(message) is False


class _FakeQuery:
    """Raises a Yahoo refusal on every call, as an unpermitted app does."""

    REFUSAL = (
        "Attempt to retrieve data at URL https://fantasysports.yahooapis.com/"
        "fantasy/v2/users;use_login=1/games;codes=nba/?format=json failed with "
        'error: "This application is not authorized to perform this action."'
    )

    league_id = "0"
    game_code = "nba"

    def get_user_games(self):
        raise YahooFantasySportsException(self.REFUSAL)


def _wrapper_that_always_refuses(monkeypatch, *, refresh_works: bool):
    """A wrapped query whose retry also refuses, with refresh succeeding or not."""
    wrapper = yahoo.TokenRefreshQueryWrapper(_FakeQuery())

    def fake_refresh(_self=None):
        if not refresh_works:
            raise RuntimeError("invalid_grant")

    monkeypatch.setattr(
        yahoo.TokenRefreshQueryWrapper, "_force_token_refresh", fake_refresh
    )
    monkeypatch.setattr(yahoo, "clear_query_cache", lambda: None)
    monkeypatch.setattr(yahoo, "_close_query_session", lambda _q: None)
    monkeypatch.setattr(
        yahoo, "YahooFantasySportsQuery", lambda **_kwargs: _FakeQuery()
    )
    monkeypatch.setenv("YAHOO_CONSUMER_KEY", "key")
    monkeypatch.setenv("YAHOO_CONSUMER_SECRET", "secret")
    return wrapper


def test_refused_after_a_successful_refresh_is_not_an_expiry(monkeypatch):
    """Yahoo honoured the refresh, so the credential is live and the app is not.

    Reporting this as an expiry sent the user to /login forever: no login can
    grant an app a permission it was never registered with.
    """
    wrapper = _wrapper_that_always_refuses(monkeypatch, refresh_works=True)

    with pytest.raises(yahoo.YahooAuthError) as excinfo:
        wrapper.get_user_games()

    assert excinfo.value.credential_valid is True
    message = str(excinfo.value)
    assert "Fantasy Sports" in message
    # Points at the approval program, the only route since 2026-07-22.
    assert "sports.yahoo.com/developer/access/" in message


def test_refused_after_a_failed_refresh_is_still_an_expiry(monkeypatch):
    """Yahoo would not refresh, so the credential really is dead."""
    wrapper = _wrapper_that_always_refuses(monkeypatch, refresh_works=False)

    with pytest.raises(yahoo.YahooAuthError) as excinfo:
        wrapper.get_user_games()

    assert excinfo.value.credential_valid is False


def test_credential_valid_defaults_to_false():
    """Existing raise sites keep the logout behaviour they had."""
    assert yahoo.YahooAuthError("boom").credential_valid is False
