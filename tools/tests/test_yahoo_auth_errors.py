"""Tests for classifying a Yahoo error as a dead credential.

The wrapper only refreshes tokens for errors it recognises as auth failures.
Recognising too few sends a rejected token back to the caller as a 500; too
many sends unrelated failures through a pointless refresh and reports them as
a logout. Both matter, so both are pinned here.
"""

from __future__ import annotations

import pytest

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
