"""Tests for the bounded Yahoo query wrapper cache.

Verifies that evicting or clearing a cached query closes its underlying OAuth2
HTTP session, so long-running processes don't leak sockets/connection pools.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from tools.utils import yahoo


@pytest.fixture(autouse=True)
def _clear_cache():
    """Ensure each test starts and ends with an empty query cache."""
    yahoo._query_cache.clear()
    yield
    yahoo._query_cache.clear()


class _FakeWrapper:
    """Minimal stand-in wired so _close_query_session finds .oauth.session.

    _close_query_session unwraps ``wrapper.__dict__["_query"]`` then reaches
    ``.oauth.session``, so mirror that structure with a real object.
    """

    def __init__(self):
        self.session = MagicMock()
        self._query = SimpleNamespace(oauth=SimpleNamespace(session=self.session))


def _make_fake_wrapper():
    """Return a fake query wrapper whose session records close() calls."""
    wrapper = _FakeWrapper()
    return wrapper, wrapper.session


def test_eviction_closes_session_and_bounds_cache():
    """Loading more than the cap evicts the LRU entry and closes its session."""
    created = []

    def _fake_build(game_code="nba", league_id=None, league_key=None):
        wrapper, session = _make_fake_wrapper()
        created.append((league_key, wrapper, session))
        return wrapper

    with patch.object(yahoo, "_build_query_wrapper", side_effect=_fake_build):
        # Fill the cache to capacity, then add one more to force an eviction.
        for i in range(yahoo._QUERY_CACHE_MAXSIZE + 1):
            yahoo._load_query(league_key=f"nba.l.{i}")

    # Cache never exceeds the cap.
    assert len(yahoo._query_cache) == yahoo._QUERY_CACHE_MAXSIZE

    # The first (least-recently-used) wrapper was evicted and its session closed.
    _first_key, _first_wrapper, first_session = created[0]
    first_session.close.assert_called_once()

    # A still-cached wrapper's session is left open.
    _last_key, _last_wrapper, last_session = created[-1]
    last_session.close.assert_not_called()


def test_cache_hit_does_not_rebuild_or_leak():
    """A repeated key returns the cached wrapper without building a new one."""
    with patch.object(
        yahoo, "_build_query_wrapper", side_effect=lambda *_, **__: _make_fake_wrapper()[0]
    ) as mock_build:
        first = yahoo._load_query(league_key="nba.l.42")
        second = yahoo._load_query(league_key="nba.l.42")

    assert first is second
    assert mock_build.call_count == 1


def test_clear_query_cache_closes_all_sessions():
    """clear_query_cache closes every cached session and empties the cache."""
    sessions = []

    def _fake_build(game_code="nba", league_id=None, league_key=None):
        wrapper, session = _make_fake_wrapper()
        sessions.append(session)
        return wrapper

    with patch.object(yahoo, "_build_query_wrapper", side_effect=_fake_build):
        yahoo._load_query(league_key="nba.l.1")
        yahoo._load_query(league_key="nba.l.2")

    yahoo.clear_query_cache()

    assert len(yahoo._query_cache) == 0
    for session in sessions:
        session.close.assert_called_once()
