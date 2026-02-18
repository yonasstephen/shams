"""Yahoo Fantasy Sports integration helpers."""

from __future__ import annotations

import logging
import os
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from dotenv import load_dotenv

logger = logging.getLogger(__name__)
from yfpy.exceptions import YahooFantasySportsException
from yfpy.models import Matchup, Player, Scoreboard, Settings, Stat
from yfpy.query import YahooFantasySportsQuery

# Token encryption removed - tokens stored as plain text in ~/.shams/yahoo/

DEFAULT_TOKEN_DIR = Path(
    os.environ.get("SHAMS_YAHOO_TOKEN_DIR", "~/.shams/yahoo")
).expanduser()
WAIVER_BATCH_SIZE = int(os.environ.get("WAIVER_BATCH_SIZE", 25))  # Yahoo API caps at 25


class TokenRefreshQueryWrapper:
    """Wrapper around YahooFantasySportsQuery that automatically handles token expiration.

    This wrapper intercepts all method calls to the query object and automatically
    retries with fresh tokens if an OAuth token expiration error occurs.
    """

    def __init__(self, query: YahooFantasySportsQuery):
        self._query = query

    def _force_token_refresh(self):
        """Manually refresh OAuth tokens using the refresh token."""
        import requests
        from dotenv import load_dotenv

        # Use the DEFAULT_TOKEN_DIR instead of trying to access the query's attribute
        env_file = DEFAULT_TOKEN_DIR / ".env"
        if not env_file.exists():
            print(f"[WARNING] .env file not found at {env_file}")
            return

        load_dotenv(env_file)
        refresh_token = os.getenv("YAHOO_REFRESH_TOKEN")
        consumer_key = os.getenv("YAHOO_CONSUMER_KEY")
        consumer_secret = os.getenv("YAHOO_CONSUMER_SECRET")

        if not refresh_token:
            print(f"[WARNING] No refresh token found in .env file")
            return

        # Call Yahoo OAuth to refresh the token
        token_url = "https://api.login.yahoo.com/oauth2/get_token"
        token_data = {
            "client_id": consumer_key,
            "client_secret": consumer_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }

        print(f"[DEBUG] Manually refreshing OAuth tokens...")
        response = requests.post(token_url, data=token_data)
        response.raise_for_status()
        new_tokens = response.json()

        # Preserve refresh_token if not returned
        if "refresh_token" not in new_tokens:
            new_tokens["refresh_token"] = refresh_token

        # Write new tokens to .env file with created timestamp (plain text)
        # Use atomic write to prevent file corruption from concurrent writes
        import time
        from tools.utils.file_utils import write_env_file

        token_created_at = time.time()

        env_vars = {
            "YAHOO_ACCESS_TOKEN": new_tokens.get("access_token", ""),
            "YAHOO_REFRESH_TOKEN": new_tokens.get("refresh_token", ""),
            "YAHOO_TOKEN_TYPE": new_tokens.get("token_type", "bearer"),
            "YAHOO_TOKEN_EXPIRES_IN": str(new_tokens.get("expires_in", 3600)),
            "YAHOO_TOKEN_CREATED_AT": str(token_created_at),
        }
        write_env_file(env_file, env_vars)

        print(f"[DEBUG] Tokens manually refreshed and saved to {env_file}")

    def __getattr__(self, name):
        """Intercept all method calls to the wrapped query object."""
        attr = getattr(self._query, name)

        # If it's not a callable method, just return it
        if not callable(attr):
            return attr

        # Wrap callable methods with retry logic
        def wrapper(*args, **kwargs):
            retry_attempted = False
            try:
                return attr(*args, **kwargs)
            except YahooFantasySportsException as exc:
                error_msg = str(exc)
                # Check if this is a token expiration error
                if (
                    "token_expired" in error_msg or "oauth_problem" in error_msg
                ) and not retry_attempted:
                    print(
                        f"[DEBUG] Token expired during {name}, clearing cache and retrying..."
                    )
                    retry_attempted = True

                    # Clear the cache to force fresh query creation
                    clear_query_cache()

                    # Force token refresh by manually calling OAuth refresh
                    # This is a fallback in case backend didn't catch the expiration
                    try:
                        self._force_token_refresh()
                    except Exception as refresh_err:
                        print(f"[WARNING] Manual token refresh failed: {refresh_err}")

                    # Reload environment variables to pick up refreshed tokens
                    # Must specify the correct path where tokens were saved
                    load_dotenv(DEFAULT_TOKEN_DIR / ".env", override=True)

                    # Small delay to ensure .env file is written
                    import time

                    time.sleep(0.2)

                    # Get consumer credentials from environment (just reloaded)
                    consumer_key = os.environ.get("YAHOO_CONSUMER_KEY")
                    consumer_secret = os.environ.get("YAHOO_CONSUMER_SECRET")

                    if not consumer_key or not consumer_secret:
                        raise YahooAuthError(
                            "Yahoo credentials missing after token refresh. "
                            "Please set YAHOO_CONSUMER_KEY and YAHOO_CONSUMER_SECRET."
                        ) from exc

                    # Get a fresh query object and retry
                    # Note: We get the underlying _query, not a wrapped one, to avoid recursion
                    fresh_base_query = YahooFantasySportsQuery(
                        league_id=self._query.league_id,
                        game_code=self._query.game_code,
                        yahoo_consumer_key=consumer_key,
                        yahoo_consumer_secret=consumer_secret,
                        env_var_fallback=True,
                        env_file_location=_ensure_token_dir(),
                        save_token_data_to_env_file=True,
                        browser_callback=True,
                    )
                    if hasattr(self._query, "league_key"):
                        fresh_base_query.league_key = self._query.league_key

                    # Call the method on the fresh query (not wrapped, to avoid retry recursion)
                    fresh_attr = getattr(fresh_base_query, name)
                    try:
                        result = fresh_attr(*args, **kwargs)
                        print(f"[DEBUG] Retry successful for {name}")
                        return result
                    except YahooFantasySportsException as retry_exc:
                        # If retry also fails, raise as YahooAuthError
                        print(f"[DEBUG] Retry failed for {name}: {str(retry_exc)}")
                        raise YahooAuthError(
                            f"Token refresh failed: {str(retry_exc)}"
                        ) from retry_exc
                # Not a token/auth error — re-raise as the original Yahoo exception
                # so callers receive a 500-level error rather than a 401 logout
                raise

        return wrapper


def _ensure_token_dir() -> Path:
    DEFAULT_TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    return DEFAULT_TOKEN_DIR


class YahooAuthError(Exception):
    """Raised when authentication with Yahoo fails."""


def _parse_league_id(league_key: str) -> Optional[str]:
    try:
        _, raw_id = league_key.split(".l.", 1)
        return raw_id.split(".")[0]
    except ValueError:
        return None


def clear_query_cache():
    """Clear the cached YahooFantasySportsQuery objects.

    This should be called when tokens are refreshed to force recreation
    of query objects with new OAuth credentials.
    """
    _load_query.cache_clear()


@lru_cache(maxsize=8)
def _load_query(  # noqa: PLR0913
    game_code: str = "nba",
    league_id: Optional[str] = None,
    league_key: Optional[str] = None,
) -> TokenRefreshQueryWrapper:
    load_dotenv()
    consumer_key = os.environ.get("YAHOO_CONSUMER_KEY")
    consumer_secret = os.environ.get("YAHOO_CONSUMER_SECRET")

    if not consumer_key or not consumer_secret:
        raise YahooAuthError(
            "Yahoo credentials missing. Please set YAHOO_CONSUMER_KEY and YAHOO_CONSUMER_SECRET."
        )

    resolved_league_id = (
        league_id or (league_key and _parse_league_id(league_key)) or "0"
    )

    # Sanitize the .env file before yfpy reads it
    # This fixes a bug in yfpy where it can't handle malformed lines
    token_dir = _ensure_token_dir()
    env_file = token_dir / ".env"
    from tools.utils.file_utils import sanitize_env_file
    sanitize_env_file(env_file)

    query = YahooFantasySportsQuery(
        league_id=resolved_league_id,
        game_code=game_code,
        yahoo_consumer_key=consumer_key,
        yahoo_consumer_secret=consumer_secret,
        env_var_fallback=True,
        env_file_location=token_dir,
        save_token_data_to_env_file=True,
        browser_callback=True,
    )

    if league_key:
        query.league_key = league_key

    # Wrap the query with automatic token refresh handling
    return TokenRefreshQueryWrapper(query)


def fetch_user_leagues() -> Sequence[dict]:
    """Retrieve NBA leagues for the authenticated user."""
    query = _load_query(game_code="nba")
    leagues = query.get_user_leagues_by_game_key("nba")
    return [league.serialized() for league in leagues]


def _serialize_player(player) -> Optional[dict]:
    """Safely serialize a player object to a dictionary.

    Args:
        player: Player object or dict

    Returns:
        Serialized player dict or None if serialization fails
    """
    result = None

    if isinstance(player, dict):
        result = player
    elif hasattr(player, "serialized"):
        try:
            result = player.serialized()
        except Exception:
            return None
    else:
        # Try to convert to dict
        try:
            result = dict(player)
        except (TypeError, ValueError):
            return None

    # Handle case where serialized dict contains a nested "player" key with unserialized object
    if result and isinstance(result, dict) and "player" in result:
        nested = result.get("player")
        if hasattr(nested, "serialized"):
            try:
                result = nested.serialized()
            except Exception:
                return None
        elif isinstance(nested, dict):
            result = nested

    return result


def fetch_free_agents(
    league_key: str, count: int = 50, start: int = 0
) -> Sequence[dict]:
    """Fetch available players (free agents and waivers) from the league.

    Fetches players with status=FA (free agents) or status=W (waivers) -
    all unrostered players that can be acquired.

    Args:
        league_key: The Yahoo league key
        count: Maximum number of players to retrieve per status
        start: Starting index for pagination (0-based)

    Returns:
        List of player dictionaries with 'availability_status' field

    Based on Yahoo API docs: https://developer.yahoo.com/fantasysports/guide/#players-collection
    """
    query = _load_query(league_key=league_key)
    all_players = []

    for status in ["FA", "W"]:
        try:
            url = (
                f"https://fantasysports.yahooapis.com/fantasy/v2/league/{league_key}/players;"
                f"status={status};start={start};count={count}"
            )

            player_data = query.query(url, ["league", "players"])

            if player_data:
                players_list = (
                    player_data if isinstance(player_data, list) else [player_data]
                )

                for player in players_list:
                    serialized = _serialize_player(player)
                    if serialized:
                        # Tag with availability status
                        serialized["availability_status"] = status
                        all_players.append(serialized)
        except Exception:
            continue

    return all_players


def _fetch_single_status(
    league_key: str, status: str, count: int, start: int
) -> List[dict]:
    """Helper to fetch players for a single status.

    Args:
        league_key: The Yahoo league key
        status: Player status ('FA' or 'W')
        count: Number of players to fetch
        start: Starting index for pagination

    Returns:
        List of player dictionaries with 'availability_status' field added
    """
    query = _load_query(league_key=league_key)

    try:
        url = (
            f"https://fantasysports.yahooapis.com/fantasy/v2/league/{league_key}/players;"
            f"status={status};start={start};count={count}"
        )
        
        logger.info(f"Fetching waiver players: status={status}, start={start}, count={count}")

        player_data = query.query(url, ["league", "players"])

        if not player_data:
            logger.debug(f"No player data returned for status={status}, start={start}")
            return []

        players_list = player_data if isinstance(player_data, list) else [player_data]
        serialized_players = []

        for player in players_list:
            serialized = _serialize_player(player)
            if serialized:
                # Tag with availability status
                serialized["availability_status"] = status
                serialized_players.append(serialized)

        logger.info(f"Fetched {len(serialized_players)} players with status={status} at start={start}")
        return serialized_players
    except Exception as e:
        # Log the error for debugging - "No data found" errors are common when
        # pagination reaches the end or when Yahoo API has issues
        error_msg = str(e)
        if "No data found" in error_msg:
            # This happens when:
            # 1. Pagination reaches the end (normal)
            # 2. No players exist with this status at start=0 (league-specific)
            if start == 0:
                logger.info(f"No {status} players found in this league (this may be normal if all players are rostered)")
            else:
                logger.debug(f"End of pagination for status={status} at start={start}")
        else:
            logger.warning(f"Error fetching {status} players at start={start}: {error_msg}")
        return []


def fetch_free_agents_and_waivers(
    league_key: str, batch_size: Optional[int] = None
) -> List[dict]:
    """Fetch ALL available players using pagination.

    Iterates through all available players (FA and W status) separately to avoid
    pagination conflicts. Each status is paginated independently.
    
    Falls back to "A" (all available) status if both FA and W return empty.

    Args:
        league_key: The Yahoo league key
        batch_size: Number of players to fetch per batch. If None, uses WAIVER_BATCH_SIZE
                   environment variable (default: 50)

    Returns:
        Complete list of all available player dictionaries
    """
    if batch_size is None:
        batch_size = WAIVER_BATCH_SIZE

    all_players: List[dict] = []

    # Fetch each status separately with its own pagination
    for status in ["FA", "W"]:
        start = 0
        max_attempts = 50  # Safety limit per status
        attempts = 0

        while attempts < max_attempts:
            try:
                # Fetch single status at a time
                batch = _fetch_single_status(
                    league_key, status, count=batch_size, start=start
                )

                if not batch:
                    break

                all_players.extend(batch)
                start += len(batch)
                attempts += 1

            except Exception:
                break

    # Fallback: If both FA and W returned nothing, try "A" (all available) status
    # Some leagues may have different configurations where A works better
    if not all_players:
        logger.info("FA and W statuses returned no players, trying 'A' (all available) status")
        start = 0
        max_attempts = 50
        attempts = 0
        
        while attempts < max_attempts:
            try:
                batch = _fetch_single_status(
                    league_key, "A", count=batch_size, start=start
                )
                
                if not batch:
                    break
                
                all_players.extend(batch)
                start += len(batch)
                attempts += 1
            except Exception:
                break
        
        if all_players:
            logger.info(f"Successfully fetched {len(all_players)} players using 'A' status")
        else:
            logger.warning("No available players found in this league with any status (FA, W, or A)")

    return all_players


def fetch_all_player_rankings(
    league_key: str,
    batch_size: int = 25,
    max_players: Optional[int] = None,
) -> List[dict]:
    """Fetch ALL players sorted by Yahoo Actual Rank (AR) with pagination.

    Uses Yahoo API with sort=AR to get players in ranking order.
    The rank is derived from the position in the sorted results (1-indexed).

    Args:
        league_key: The Yahoo league key
        batch_size: Number of players to fetch per API call (default: 25, Yahoo's max)
        max_players: Maximum number of players to fetch. If None, fetches all.

    Returns:
        List of player dictionaries with 'rank' field added (1-indexed)
    """
    query = _load_query(league_key=league_key)
    all_players: List[dict] = []
    start = 0
    max_attempts = 100  # Safety limit to prevent infinite loops

    logger.info(f"Fetching player rankings with batch_size={batch_size}, max_players={max_players}")

    for _ in range(max_attempts):
        try:
            # Fetch players sorted by Actual Rank
            url = (
                f"https://fantasysports.yahooapis.com/fantasy/v2/league/{league_key}/players;"
                f"sort=AR;start={start};count={batch_size}"
            )

            player_data = query.query(url, ["league", "players"])

            if not player_data:
                logger.debug(f"No player data returned at start={start}")
                break

            players_list = player_data if isinstance(player_data, list) else [player_data]
            
            if not players_list:
                logger.debug(f"Empty players list at start={start}")
                break

            batch_count = 0
            for player in players_list:
                serialized = _serialize_player(player)
                if serialized:
                    # Add rank based on position in sorted results (1-indexed)
                    serialized["rank"] = len(all_players) + 1
                    all_players.append(serialized)
                    batch_count += 1

                    # Check if we've reached max_players limit
                    if max_players and len(all_players) >= max_players:
                        logger.info(f"Reached max_players limit: {len(all_players)} players fetched")
                        return all_players

            logger.debug(f"Fetched {batch_count} players at start={start}, total={len(all_players)}")

            # Move to next batch
            start += len(players_list)

            # If we got fewer players than requested, we've reached the end
            if len(players_list) < batch_size:
                logger.debug(f"Reached end of data: got {len(players_list)} players, expected {batch_size}")
                break

        except Exception as e:
            logger.warning(f"Error fetching player rankings at offset {start}: {e}")
            break

    logger.info(f"Completed fetching player rankings: {len(all_players)} total players")
    return all_players


def fetch_user_team_key(league_key: str) -> str:
    """Return the Yahoo team key for the logged-in user's team in the league."""
    query = _load_query(league_key=league_key)
    teams = query.get_user_teams()
    for entry in teams:
        game = entry
        if isinstance(entry, dict):
            game = entry.get("game", entry)
        elif hasattr(entry, "serialized"):
            game = entry.serialized()

        teams_list: Sequence = []
        if isinstance(game, dict):
            teams_list = game.get("teams", [])
        else:
            teams_list = getattr(game, "teams", [])

        for team_entry in teams_list:
            team_obj = team_entry
            if isinstance(team_entry, dict):
                team_obj = team_entry.get("team", team_entry)
            elif hasattr(team_entry, "serialized"):
                team_obj = team_entry.serialized()

            if isinstance(team_obj, dict):
                team_key = team_obj.get("team_key")
            else:
                team_key = getattr(team_obj, "team_key", None)

            if isinstance(team_key, bytes):
                team_key = team_key.decode("utf-8")

            if isinstance(team_key, str) and team_key.startswith(league_key):
                return team_key
    raise YahooAuthError("Unable to locate user team for league")


def extract_team_id(team_key: str) -> int:
    try:
        return int(team_key.split(".t.", 1)[1])
    except (ValueError, IndexError) as exc:  # pragma: no cover - defensive
        raise YahooAuthError(f"Invalid team key: {team_key}") from exc


def fetch_league_scoreboard(league_key: str, week: int) -> Scoreboard:
    query = _load_query(league_key=league_key)
    return query.get_league_scoreboard_by_week(week)


def fetch_team_matchups(league_key: str, team_id: int) -> Sequence[Matchup]:
    query = _load_query(league_key=league_key)
    return query.get_team_matchups(team_id)


def fetch_team_roster_for_date(
    league_key: str, team_id: int, target_date: date
) -> Sequence[Player]:
    query = _load_query(league_key=league_key)
    return query.get_team_roster_player_info_by_date(team_id, target_date.isoformat())


def fetch_player_season_stats(league_key: str, player_key: str) -> Player:
    query = _load_query(league_key=league_key)
    return query.get_player_stats_for_season(player_key)


def fetch_matchup_for_team(league_key: str, team_key: str, week: int) -> Matchup:
    scoreboard = fetch_league_scoreboard(league_key, week)
    for matchup_entry in scoreboard.matchups:
        matchup = (
            matchup_entry.get("matchup")
            if isinstance(matchup_entry, dict)
            else matchup_entry
        )
        if not matchup:
            continue
        teams_list = getattr(matchup, "teams", [])
        for team_entry in teams_list:
            if isinstance(team_entry, dict):
                team = team_entry.get("team", team_entry)
            else:
                team = team_entry
            team_data = team.serialized() if hasattr(team, "serialized") else team
            if isinstance(team_data, dict) and team_data.get("team_key") == team_key:
                return matchup
    raise YahooAuthError("Unable to locate matchup for team")


def _serialize_team_points(container: object) -> Dict[str, float]:
    if hasattr(container, "serialized"):
        container = container.serialized()
    if isinstance(container, dict):
        return container
    if container is None:
        return {}
    try:
        return container.__dict__
    except AttributeError:  # pragma: no cover - defensive
        return {}


def fetch_team_stats_for_week(
    league_key: str,
    team_id: int,
    week: int,
) -> Dict[str, Dict[str, float]]:
    """Return weekly stat totals for a team, combining actual and projected values."""

    query = _load_query(league_key=league_key)
    data = query.get_team_stats_by_week(team_id, week)

    if hasattr(data, "serialized"):
        data = data.serialized()
    if not isinstance(data, dict):
        raise YahooAuthError("Unexpected response from Yahoo get_team_stats_by_week")

    def _extract_stats(key: str) -> Dict[str, float]:
        container = data.get(key)
        if hasattr(container, "serialized"):
            container = container.serialized()
        stats_list = []
        if isinstance(container, dict):
            stats_list = container.get("stats", [])
        elif hasattr(container, "stats"):
            stats_list = container.stats
        totals: Dict[str, float] = {}
        for entry in stats_list or []:
            stat_obj = entry.get("stat") if isinstance(entry, dict) else entry
            if hasattr(stat_obj, "serialized"):
                stat_obj = stat_obj.serialized()
            if not isinstance(stat_obj, dict):
                continue
            stat_id = str(stat_obj.get("stat_id"))
            try:
                totals[stat_id] = float(stat_obj.get("value", 0.0))
            except (TypeError, ValueError):
                totals[stat_id] = 0.0
        return totals

    result = {
        "team_points": _serialize_team_points(data.get("team_points")),
        "team_stats": _extract_stats("team_stats"),
        "team_projected": _extract_stats("team_projected_points"),
    }
    return result


def determine_current_week(league_key: str, team_id: int) -> int:
    matchups = fetch_team_matchups(league_key, team_id)
    last_week = None
    for entry in matchups:
        matchup = entry.get("matchup") if isinstance(entry, dict) else entry
        if not matchup:
            continue
        try:
            week_value = int(matchup.week)
        except (TypeError, ValueError):
            continue
        last_week = week_value
        if matchup.status not in {"postevent", "final"}:
            return week_value
    if last_week is not None:
        return last_week
    raise YahooAuthError("Unable to determine current matchup week")


def fetch_matchup_context(
    league_key: str, team_key: str, week: Optional[int] = None
) -> Tuple[Matchup, Scoreboard]:
    team_id = extract_team_id(team_key)
    resolved_week = week or determine_current_week(league_key, team_id)
    scoreboard = fetch_league_scoreboard(league_key, resolved_week)
    matchup = fetch_matchup_for_team(league_key, team_key, resolved_week)
    return matchup, scoreboard


def fetch_league_settings(league_key: str) -> Settings:
    query = _load_query(league_key=league_key)
    return query.get_league_settings()


def fetch_league_stat_categories(league_key: str) -> Sequence[Dict[str, object]]:
    settings = fetch_league_settings(league_key)
    stat_categories = getattr(settings, "stat_categories", None)
    stats: Iterable[Stat] = (
        getattr(stat_categories, "stats", []) if stat_categories else []
    )

    result: List[Dict[str, object]] = []
    for stat in stats:
        serialized = stat.serialized() if hasattr(stat, "serialized") else stat
        if isinstance(serialized, dict):
            result.append(serialized)
    return result


def fetch_and_cache_league_roster_positions(league_key: str) -> List[str]:
    """Fetch league roster position slots from Yahoo API and cache them.

    Args:
        league_key: Yahoo league key

    Returns:
        List of position slot strings (e.g., ["PG", "SG", "G", "SF", "PF", "F", "C", "Util", "Util", "BN", "BN", "IL"])
    """
    from tools.utils import league_cache

    # Check cache first
    cached_positions = league_cache.load_league_roster_settings(league_key)
    if cached_positions is not None:
        logger.debug(f"Using cached roster positions for league {league_key}: {cached_positions}")
        return cached_positions

    # Fetch from Yahoo API
    logger.debug(f"Fetching roster positions from Yahoo API for league {league_key}")
    try:
        settings = fetch_league_settings(league_key)
    except Exception as e:
        logger.error(f"Failed to fetch league settings: {e}")
        return []

    roster_positions: List[str] = []

    # Extract roster positions from settings
    # The settings object has a roster_positions attribute that contains the position slots
    if hasattr(settings, "roster_positions") and settings.roster_positions:
        roster_pos_list = settings.roster_positions
        
        logger.debug(f"Parsing roster_positions list with {len(roster_pos_list)} entries")

        # Parse each position entry (should be RosterPosition objects)
        for pos_entry in roster_pos_list:
            position = None
            count = 1
            
            # Try to get position and count from the object
            if hasattr(pos_entry, "position"):
                position = str(pos_entry.position)
                count = int(getattr(pos_entry, "count", 1))
                logger.debug(f"  Parsed position: {position}, count: {count}")
            elif isinstance(pos_entry, dict):
                position = pos_entry.get("position", "")
                count = int(pos_entry.get("count", 1))
            elif hasattr(pos_entry, "serialized"):
                serialized_entry = pos_entry.serialized()
                position = serialized_entry.get("position", "")
                count = int(serialized_entry.get("count", 1))
            else:
                logger.warning(f"  Could not parse position entry: {pos_entry}")
                continue

            # Add position 'count' times to the list
            if position:
                for _ in range(count):
                    roster_positions.append(position)
            else:
                logger.warning(f"  Empty position found in entry: {pos_entry}")

    # Cache the result
    if roster_positions:
        logger.info(f"Fetched {len(roster_positions)} roster positions from Yahoo API: {roster_positions}")
        league_cache.save_league_roster_settings(league_key, roster_positions)
    else:
        logger.warning(f"No roster positions found in league settings for {league_key}. Settings object: {settings}")

    return roster_positions
