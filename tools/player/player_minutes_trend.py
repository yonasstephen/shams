#!/usr/bin/env python3
"""Utilities for computing NBA minute trends using nba_api.

The minute trend is defined as the minutes played in the player's most recent
game minus the average minutes from the three games immediately preceding it.
These helpers are consumed by the interactive ``shams`` CLI.
"""

from __future__ import annotations

import difflib
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import List, Optional, Sequence, Tuple, Union

from nba_api.stats.endpoints import playerindex
from nba_api.stats.static import players as players_static

from tools.utils import nba_api_config  # noqa: F401  # pylint: disable=unused-import

SeasonType = str

SEASON_TYPE_CHOICES: Tuple[SeasonType, ...] = (
    "Regular Season",
    "Playoffs",
    "Pre Season",
    "All Star",
)

_SEASON_TYPE_LOOKUP = {
    key: value
    for value in SEASON_TYPE_CHOICES
    for key in [  # pylint: disable=use-sequence-for-iteration
        value.lower(),
        value.replace(" ", "").lower(),
        value.replace(" ", "_").lower(),
    ]
}
_SEASON_TYPE_LOOKUP.update(
    {
        "regular": "Regular Season",
        "regularseason": "Regular Season",
        "playoff": "Playoffs",
    }
)

MAX_SUGGESTION_LIMIT = 50


def _resolve_int_env(env_var: str, default: int) -> int:
    value = os.environ.get(env_var)
    if value is None:
        return default
    try:
        return int(value.split("#", 1)[0].strip())
    except (TypeError, ValueError):
        return default


NBA_API_TIMEOUT = _resolve_int_env("NBA_API_TIMEOUT", 60)


@dataclass
class TrendComputation:
    player_id: int
    player_name: str
    season_type: SeasonType
    last_minutes: float
    prior_average: float
    trend: float
    logs: List[Tuple[str, float, str]]


@dataclass
class SuggestionResponse:
    query: str
    season_type: SeasonType
    suggestions: Sequence[dict]


ResolutionResult = Union[TrendComputation, SuggestionResponse]


__all__ = [
    "MAX_SUGGESTION_LIMIT",
    "SEASON_TYPE_CHOICES",
    "SuggestionResponse",
    "TrendComputation",
    "compute_minute_trend",
    "compute_minute_trend_for_player",
    "find_player_matches",
    "normalize_season_type",
    "process_minute_trend_query",
]


def normalize_season_type(value: str) -> SeasonType:
    if not value:
        return SEASON_TYPE_CHOICES[0]

    key = value.strip().lower()
    return _SEASON_TYPE_LOOKUP.get(key, SEASON_TYPE_CHOICES[0])


def _get_current_season() -> str:
    """Get the current NBA season string (e.g., '2025-26')."""
    from datetime import date

    today = date.today()
    # NBA season starts in October, so if we're before October, use previous year
    year = today.year if today.month >= 10 else today.year - 1
    return f"{year}-{str(year + 1)[-2:]}"


@lru_cache(maxsize=1)
def get_all_players() -> List[dict]:
    """Return a cached list of all NBA players.

    Uses PlayerIndex endpoint to get current season players (active players),
    with fallback to static list if the API call fails.
    """
    try:
        season = _get_current_season()
        index = playerindex.PlayerIndex(season=season, league_id="00")
        df = index.get_data_frames()[0]

        # Convert DataFrame to list of dicts matching static players format
        players = []
        for _, row in df.iterrows():
            first_name = row.get("PLAYER_FIRST_NAME", "")
            last_name = row.get("PLAYER_LAST_NAME", "")
            full_name = f"{first_name} {last_name}".strip()
            players.append(
                {
                    "id": row["PERSON_ID"],
                    "full_name": full_name,
                    "first_name": first_name,
                    "last_name": last_name,
                    "is_active": True,  # All players from PlayerIndex are active
                }
            )
        return players
    except Exception:
        # Fallback to static players list if API fails
        return players_static.get_players()


def normalize(text: str) -> str:
    """Normalize text for comparison: lowercase and remove diacritics."""
    import unicodedata

    # Normalize unicode and strip diacritics
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return ascii_text.strip().lower()


def find_player_matches(
    query: str, limit: int = 5
) -> Tuple[Optional[int], Sequence[dict]]:
    """Resolve a player name to an NBA.com player ID.

    Returns a tuple of (player_id, suggested_matches). If player_id is None,
    the caller should use the suggested matches to prompt the user.
    """

    players = get_all_players()
    query_norm = normalize(query)

    exact_matches = [p for p in players if normalize(p["full_name"]) == query_norm]
    if exact_matches:
        return exact_matches[0]["id"], ()

    substring_matches = [p for p in players if query_norm in normalize(p["full_name"])]
    if len(substring_matches) == 1:
        return substring_matches[0]["id"], ()
    if len(substring_matches) > 1:
        return None, substring_matches[:limit]

    # Use a higher cutoff (0.75) to reduce false positives from weak matches
    # like "Steve Settle III" matching "Jimmy Butler III" due to shared suffix
    all_names = [p["full_name"] for p in players]
    close_names = difflib.get_close_matches(query, all_names, n=limit, cutoff=0.75)
    close_matches = [p for p in players if p["full_name"] in close_names]

    # Only auto-resolve fuzzy matches if the match is very strong (ratio >= 0.85)
    # This prevents false positives where names share common suffixes like "III"
    if len(close_matches) == 1:
        ratio = difflib.SequenceMatcher(
            None, query.lower(), close_matches[0]["full_name"].lower()
        ).ratio()
        if ratio >= 0.85:
            return close_matches[0]["id"], ()
        # Not confident enough - return as suggestion instead
        return None, close_matches[:limit]

    return None, close_matches[:limit]


def parse_minutes(min_value: str) -> Optional[float]:
    if min_value is None:
        return None
    if isinstance(min_value, (int, float)):
        return float(min_value)

    value = str(min_value).strip()
    if not value:
        return None

    if value.isdigit():
        return float(value)

    if ":" in value:
        try:
            minutes_part, seconds_part = value.split(":", 1)
            minutes = int(minutes_part)
            seconds = int(seconds_part)
            return minutes + seconds / 60
        except ValueError:
            return None

    lowered = value.lower()
    if lowered in {"dnp", "did not play"}:
        return 0.0

    return None


def fetch_recent_minute_logs(
    player_id: int,
    season_type: SeasonType,  # pylint: disable=unused-argument
    count: int = 4,
    timeout: int = NBA_API_TIMEOUT,  # pylint: disable=unused-argument
) -> List[Tuple[str, float, str]]:
    from datetime import date

    from nba_api.stats.library.parameters import SeasonAll

    from tools.player.player_fetcher import fetch_player_stats_from_cache
    from tools.schedule.schedule_fetcher import get_season_start_date

    # Try to use cache first
    today = date.today()
    season_start = get_season_start_date(SeasonAll.current_season)

    try:
        cached_games = fetch_player_stats_from_cache(player_id, season_start, today)

        if cached_games:
            # Use cached data
            records: List[Tuple[str, float, str]] = []

            # Sort by date descending
            sorted_games = sorted(
                cached_games, key=lambda g: g.get("date", ""), reverse=True
            )

            for game in sorted_games:
                minutes = parse_minutes(game.get("MIN"))
                if minutes is None:
                    continue
                records.append(
                    (
                        game.get("date", ""),
                        minutes,
                        game.get("matchup", game.get("MATCHUP", "")),
                    )
                )
                if len(records) >= count:
                    break

            if records:
                return records
    except Exception:
        pass

    # If no cached data, return empty (no API fallback)
    # The cache should be refreshed before calling this function
    return []


def compute_minute_trend(
    player_id: int,
    season_type: SeasonType,
    timeout: int = NBA_API_TIMEOUT,
) -> Tuple[float, float, float, List[Tuple[str, float, str]]]:
    logs = fetch_recent_minute_logs(player_id, season_type, count=4, timeout=timeout)

    if len(logs) == 0:
        raise ValueError("No games with minute data found.")

    # If we have at least 1 game, we can compute a trend
    # Missing prior games are treated as 0 minutes
    last_game = logs[0]

    # Get prior games (up to 3), pad with 0s if fewer than 3
    prior_games = logs[1:4] if len(logs) > 1 else []

    # Calculate average of prior games, treating missing games as 0
    if len(prior_games) > 0:
        average_prior = sum(game[1] for game in prior_games) / len(prior_games)
    else:
        # No prior games, so average is 0
        average_prior = 0.0

    trend = last_game[1] - average_prior

    return last_game[1], average_prior, trend, logs


def compute_minute_trend_for_player(
    player_id: int,
    player_name: str,
    season_type: SeasonType,
    timeout: int = NBA_API_TIMEOUT,
) -> TrendComputation:
    last_minutes, prior_avg, trend, logs = compute_minute_trend(
        player_id, season_type, timeout=timeout
    )
    return TrendComputation(
        player_id=player_id,
        player_name=player_name,
        season_type=season_type,
        last_minutes=last_minutes,
        prior_average=prior_avg,
        trend=trend,
        logs=logs,
    )


def process_minute_trend_query(
    player_query: str,
    season_type: SeasonType,
    suggestion_limit: int = MAX_SUGGESTION_LIMIT,
    timeout: int = NBA_API_TIMEOUT,
) -> ResolutionResult:
    player_id, suggestions = find_player_matches(player_query, limit=suggestion_limit)

    if player_id is None:
        return SuggestionResponse(
            query=player_query,
            season_type=season_type,
            suggestions=suggestions,
        )

    # We resolved the player ID. Need to obtain the canonical name from matches.
    players = get_all_players()
    player_record = next((p for p in players if p["id"] == player_id), None)
    player_name = player_record["full_name"] if player_record else player_query

    computation = compute_minute_trend_for_player(
        player_id, player_name, season_type, timeout=timeout
    )
    return computation
