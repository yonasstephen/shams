"""Tests for resolving which season's leagues to return.

Yahoo publishes a season's game key as soon as the season exists, before any
league is created in it, and answers "not authorized to perform this action"
for a game the user has no leagues in. That phrasing is indistinguishable from
a rejected token, so asking only for the active game key turned an ordinary
preseason into a forced logout on every request. These pin the walk back
through the user's own game history instead.
"""

from __future__ import annotations

import pytest
from yfpy.exceptions import YahooFantasySportsException

from tools.utils import yahoo

# The message Yahoo actually returns for a game the user has no leagues in.
NO_LEAGUES_ERROR = (
    "Attempt to retrieve data at URL https://fantasysports.yahooapis.com/"
    "fantasy/v2/users;use_login=1/games;game_keys=466/leagues/?format=json "
    'failed with error: "This application is not authorized to perform this action."'
)


class FakeGame:
    def __init__(self, game_key):
        self.game_key = game_key


class FakeLeague:
    def __init__(self, name):
        self.name = name

    def serialized(self):
        return {"name": self.name}


class FakeQuery:
    """Stands in for a yfpy query. ``leagues`` maps game_key -> result or raiser."""

    def __init__(self, game_keys, leagues):
        # yfpy returns game history ascending by season.
        self._games = [FakeGame(k) for k in game_keys]
        self._leagues = leagues
        self.asked = []

    def get_user_games(self):
        return self._games

    def get_user_leagues_by_game_key(self, game_key):
        self.asked.append(game_key)
        result = self._leagues.get(game_key)
        if isinstance(result, Exception):
            raise result
        return result or []


@pytest.fixture
def patch_query(monkeypatch):
    def _install(query):
        monkeypatch.setattr(yahoo, "_load_query", lambda **_kwargs: query)
        return query

    return _install


def test_falls_back_to_last_season_in_the_preseason(patch_query):
    """The new game key exists but is empty; last season's leagues are returned."""
    query = patch_query(
        FakeQuery(
            game_keys=["454", "466"],  # ascending: last season, then current
            leagues={
                "466": YahooFantasySportsException(NO_LEAGUES_ERROR),
                "454": [FakeLeague("Dunk Dynasty")],
            },
        )
    )

    assert yahoo.fetch_user_leagues() == [{"name": "Dunk Dynasty"}]
    # Newest first, and it stopped as soon as it found leagues.
    assert query.asked == ["466", "454"]


def test_prefers_the_newest_season_that_has_leagues(patch_query):
    query = patch_query(
        FakeQuery(
            game_keys=["454", "466"],
            leagues={
                "466": [FakeLeague("This Year")],
                "454": [FakeLeague("Last Year")],
            },
        )
    )

    assert yahoo.fetch_user_leagues() == [{"name": "This Year"}]
    assert query.asked == ["466"]


def test_no_leagues_anywhere_returns_empty_not_an_auth_error(patch_query):
    """An account with no NBA leagues is a legitimate state, not a logout."""
    patch_query(
        FakeQuery(
            game_keys=["454", "466"],
            leagues={
                "466": YahooFantasySportsException(NO_LEAGUES_ERROR),
                "454": YahooFantasySportsException(NO_LEAGUES_ERROR),
            },
        )
    )

    assert yahoo.fetch_user_leagues() == []


def test_a_missing_leagues_key_is_treated_as_an_empty_season(patch_query):
    """yfpy drills into the response with plain indexing, so a KeyError means empty."""
    query = patch_query(
        FakeQuery(
            game_keys=["454", "466"],
            leagues={
                "466": KeyError("leagues"),
                "454": [FakeLeague("Dunk Dynasty")],
            },
        )
    )

    assert yahoo.fetch_user_leagues() == [{"name": "Dunk Dynasty"}]
    assert query.asked == ["466", "454"]


def test_a_dead_credential_still_propagates(patch_query):
    """A rejected token must not be mistaken for an empty season."""
    query = patch_query(
        FakeQuery(
            game_keys=["454", "466"],
            leagues={
                "466": yahoo.YahooAuthError("Token refresh failed: invalid_grant"),
                "454": [FakeLeague("Never Reached")],
            },
        )
    )

    with pytest.raises(yahoo.YahooAuthError):
        yahoo.fetch_user_leagues()
    # Stopped at the first season: probing the rest would refresh once per season.
    assert query.asked == ["466"]


def test_no_game_history_returns_empty(patch_query):
    patch_query(FakeQuery(game_keys=[], leagues={}))
    assert yahoo.fetch_user_leagues() == []


def test_single_league_not_wrapped_in_a_list(patch_query):
    """yfpy hands back a bare object when a game has exactly one league."""
    patch_query(
        FakeQuery(game_keys=["466"], leagues={"466": FakeLeague("Solo League")})
    )

    assert yahoo.fetch_user_leagues() == [{"name": "Solo League"}]
