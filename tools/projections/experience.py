"""Seasons of NBA experience, as a stand-in for age.

Age matters for projection — young players grow into minutes, veterans lose
them — but the box score cache has no birthdates, and fetching them player by
player would be several hundred API calls.

``commonallplayers`` returns every player's debut year in a *single* request, so
experience comes essentially free. It is a proxy, not age: two players drafted
the same year can be three years apart. Good enough for a gentle minutes
adjustment, not good enough to build a real aging curve on.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


def _cache_path(season: str) -> Path:
    """Where the debut-year table is cached."""
    directory = Path.home() / ".shams" / "projections"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"debut_years_{season}.json"


def _season_start_year(season: str) -> int:
    """First year of a season string such as ``2024-25``."""
    return int(season.split("-")[0])


def fetch_debut_years(season: str, use_cache: bool = True) -> Dict[int, int]:
    """Map NBA player id to debut year.

    Args:
        season: Season to query, e.g. ``2024-25``.
        use_cache: Read from and write to the local cache.

    Returns:
        Player id -> debut year. Empty when the API is unreachable, which
        degrades the projection to experience-neutral rather than failing.
    """
    path = _cache_path(season)
    if use_cache and path.exists():
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return {int(k): int(v) for k, v in json.load(handle).items()}
        except (json.JSONDecodeError, OSError, ValueError):
            logger.warning("Debut-year cache unreadable, refetching")

    try:
        from nba_api.stats.endpoints import commonallplayers

        response = commonallplayers.CommonAllPlayers(
            season=season, is_only_current_season=0
        )
        rows = response.get_normalized_dict()["CommonAllPlayers"]
    except Exception as exc:  # pylint: disable=broad-except
        # Experience is an refinement, never a hard dependency.
        logger.warning("Could not fetch debut years: %s", exc)
        return {}

    debut: Dict[int, int] = {}
    for row in rows:
        try:
            player_id = int(row["PERSON_ID"])
            from_year = int(row["FROM_YEAR"])
        except (KeyError, TypeError, ValueError):
            continue
        debut[player_id] = from_year

    if use_cache and debut:
        try:
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({str(k): v for k, v in debut.items()}, handle)
        except OSError as exc:
            logger.warning("Could not cache debut years: %s", exc)

    return debut


def experience_map(
    target_season: str, debut_years: Optional[Dict[int, int]] = None
) -> Dict[int, int]:
    """Seasons of experience each player will have in ``target_season``.

    Args:
        target_season: The season being projected, e.g. ``2025-26``.
        debut_years: Optional precomputed debut years; fetched if omitted.

    Returns:
        Player id -> experience, where 0 means a rookie season.
    """
    if debut_years is None:
        debut_years = fetch_debut_years(target_season)

    target_year = _season_start_year(target_season)
    return {
        player_id: max(target_year - from_year, 0)
        for player_id, from_year in debut_years.items()
    }
