#!/usr/bin/env python
"""Build the static NBA data feed consumed by the season Chrome extension.

The extension holds an authenticated Yahoo session in the browser, so it can read
league, roster and scoreboard data on its own. What it cannot get is the NBA side:
per-game averages, game logs and the schedule. This script turns the local
``~/.shams`` cache into a handful of small gzipped JSON files the extension fetches
and caches, which is what lets the projection run with no server at runtime.

Nothing here talks to the network. It reads what ``/refresh`` and
``scripts/build_projections.py`` already produced, so run those first.

Usage:
    pipenv run python scripts/build_feed.py 2026-27
    pipenv run python scripts/build_feed.py 2026-27 --out feed --tail-days 35
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.boxscore import boxscore_cache
from tools.projections import export
from tools.schedule import schedule_cache
from tools.utils.player_index import get_index_snapshot, normalize_player_name
from tools.utils.season import get_current_season

#: Bumped whenever the shape of a feed file changes incompatibly.
SCHEMA_VERSION = 1

#: Per-game fields carried for every projected player, in CSV column order.
PROJECTION_STATS = (
    "gp", "mpg", "fgm", "fga", "fg_pct", "ftm", "fta", "ft_pct",
    "threes", "points", "rebounds", "assists", "steals", "blocks", "turnovers",
)

#: Season-average fields as ``boxscore_cache.compute_season_averages`` returns them.
SEASON_STATS = (
    "games_played", "fgm", "fga", "fg_pct", "ftm", "fta", "ft_pct",
    "threes", "points", "rebounds", "assists", "steals", "blocks", "turnovers",
)

#: Column order of each compacted game-log row in ``players.json.gz``.
GAME_FIELDS = (
    "date", "min", "fgm", "fga", "ftm", "fta", "threes",
    "points", "rebounds", "assists", "steals", "blocks", "turnovers",
)

#: Box-score keys behind each ``GAME_FIELDS`` entry after ``date``.
_GAME_SOURCE_KEYS = (
    "MIN", "FGM", "FGA", "FTM", "FTA", "FG3M",
    "PTS", "REB", "AST", "STL", "BLK", "TO",
)


def previous_season(season: str) -> str:
    """The season before ``season`` ('2026-27' -> '2025-26')."""
    start = int(season.split("-")[0]) - 1
    return f"{start}-{str(start + 1)[-2:]}"


def _parse_minutes(value: object) -> float:
    """Minutes as a float, from either '31:24' or a bare number."""
    if value in (None, ""):
        return 0.0
    text = str(value)
    if ":" in text:
        minutes, _, seconds = text.partition(":")
        try:
            return round(float(minutes) + float(seconds) / 60.0, 2)
        except ValueError:
            return 0.0
    try:
        return round(float(text), 2)
    except ValueError:
        return 0.0


def _number(value: object) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _round_stats(stats: Dict[str, object], fields: Sequence[str]) -> Dict[str, float]:
    return {field: round(_number(stats.get(field)), 4) for field in fields}


def _player_ids_with_games(season: str) -> List[int]:
    """NBA ids that have a cached game log this season, from the cache filenames."""
    players_dir = boxscore_cache.get_cache_dir() / "players" / season
    if not players_dir.exists():
        return []

    ids: List[int] = []
    for path in sorted(players_dir.glob("*.json")):
        prefix = path.stem.split("_", 1)[0]
        if prefix.isdigit():
            ids.append(int(prefix))
    return ids


def _compact_game(game: Dict[str, object]) -> Optional[List[object]]:
    """One game log row as a positional list matching ``GAME_FIELDS``."""
    game_date = game.get("date")
    if not game_date:
        return None

    row: List[object] = [game_date, _parse_minutes(game.get("MIN"))]
    row.extend(round(_number(game.get(key)), 2) for key in _GAME_SOURCE_KEYS[1:])
    return row


def build_projections(season: str) -> Dict[str, object]:
    """Preseason baseline: the Marcel+residual projection, keyed by NBA id."""
    rows = export.load_projections(season)
    players: Dict[str, object] = {}

    for row in rows:
        nba_id = str(row.get("nba_id") or "").strip()
        if not nba_id:
            continue

        entry: Dict[str, object] = {
            "name": row.get("name") or "",
            "team": row.get("team") or "",
            "positions": row.get("positions") or "",
            "stats": _round_stats(row, PROJECTION_STATS),
            "confidence": round(_number(row.get("confidence")), 3),
        }
        yahoo_id = str(row.get("yahoo_id") or "").strip()
        if yahoo_id:
            entry["yahoo_id"] = yahoo_id
        players[nba_id] = entry

    return {"season": season, "count": len(players), "players": players}


def build_players(season: str, tail_days: int, today: date) -> Dict[str, object]:
    """Season averages plus a recent game-log tail, keyed by NBA id.

    The tail is raw rather than pre-averaged on purpose: the extension computes the
    ``last3``/``last7``/``last7d``/``last30d`` windows itself, relative to the day it
    runs, so a feed that is a day or two stale still produces correct windows.

    Both are computed from the games up to ``today`` only, so a historical rebuild
    (``--today`` in the past) sees the season as it stood that day.
    """
    cutoff = (today - timedelta(days=tail_days)).isoformat()
    anchor = today.isoformat()
    players: Dict[str, object] = {}

    for nba_id in _player_ids_with_games(season):
        cached = boxscore_cache.load_player_games(nba_id, season) or {}
        # Games after the anchor must not leak into a historical rebuild, which is how
        # fixture and backtest feeds are produced: not into the tail, and not into the
        # season average, which is why it is computed here rather than loaded.
        games = [game for game in cached.get("games") or [] if str(game.get("date") or "") <= anchor]
        if not games:
            continue

        tail: List[List[object]] = []
        for game in games:
            if str(game.get("date") or "") < cutoff:
                continue
            compacted = _compact_game(game)
            if compacted:
                tail.append(compacted)
        tail.sort(key=lambda row: row[0])

        season_avg = _round_stats(boxscore_cache.compute_season_averages(games), SEASON_STATS)
        # The cache's season average carries no minutes; the tail is too short for "season".
        season_avg["mpg"] = round(sum(_parse_minutes(game.get("MIN")) for game in games) / len(games), 2)

        entry: Dict[str, object] = {
            "name": cached.get("player_name") or "",
            "games": tail,
            "season_avg": season_avg,
        }
        eligibility = boxscore_cache.load_player_eligibility(nba_id, season)
        if eligibility:
            entry["eligible_positions"] = eligibility
        players[str(nba_id)] = entry

    return {
        "season": season,
        "tail_days": tail_days,
        "tail_start": cutoff,
        "fields": list(GAME_FIELDS),
        "count": len(players),
        "players": players,
    }


def build_schedule(season: str) -> Dict[str, object]:
    """Date -> games, compacted to the tricodes the extension joins on."""
    full = schedule_cache.load_full_schedule(season) or {}
    date_games = full.get("date_games") or {}

    dates: Dict[str, List[List[object]]] = {}
    total = 0
    for game_date in sorted(date_games):
        rows: List[List[object]] = []
        for game in date_games[game_date]:
            rows.append([
                game.get("home_team_tricode") or "",
                game.get("away_team_tricode") or "",
                game.get("game_id") or "",
                game.get("postponed_status") or "N",
            ])
        if rows:
            dates[game_date] = rows
            total += len(rows)

    return {
        "season": season,
        "fields": ["home", "away", "game_id", "postponed"],
        "game_count": total,
        "dates": dates,
    }


def _name_lookup() -> Dict[str, str]:
    """Normalized name -> NBA id for every active player.

    The Yahoo id index only covers players some past waiver or ranking run happened to
    touch, so it misses most rosters. The Python engine resolves players by name
    (``player_fetcher.player_id_lookup``); shipping the same lookup keeps the extension
    able to join a Yahoo roster to NBA stats for anyone, not just the indexed few.
    """
    from nba_api.stats.static import players as nba_players

    lookup: Dict[str, str] = {}
    for player in nba_players.get_players():
        if not player.get("is_active"):
            continue
        lookup[normalize_player_name(player["full_name"])] = str(player["id"])
    return lookup


def build_player_index(projections: Dict[str, object]) -> Dict[str, object]:
    """Yahoo id -> NBA id, from the shared index plus any ids the CSV carries."""
    snapshot = get_index_snapshot()
    mapping: Dict[str, str] = {}

    for yahoo_id, nba_id in (snapshot.get("yahoo_id_to_nba_id") or {}).items():
        if nba_id is not None:
            mapping[str(yahoo_id)] = str(nba_id)

    for nba_id, entry in (projections.get("players") or {}).items():
        yahoo_id = entry.get("yahoo_id") if isinstance(entry, dict) else None
        if yahoo_id:
            mapping.setdefault(str(yahoo_id), str(nba_id))

    names = {
        str(nba_id): entry.get("name", "")
        for nba_id, entry in (projections.get("players") or {}).items()
        if isinstance(entry, dict)
    }

    by_name = _name_lookup()
    # Anyone the projection CSV knows but the static list does not (rookies mid-update).
    for nba_id, entry in (projections.get("players") or {}).items():
        if isinstance(entry, dict) and entry.get("name"):
            by_name.setdefault(normalize_player_name(str(entry["name"])), str(nba_id))

    return {
        "count": len(mapping),
        "name_count": len(by_name),
        "yahoo_to_nba": mapping,
        "name_to_nba": by_name,
        "nba_names": names,
    }


def _write_gzip(path: Path, payload: object) -> Dict[str, object]:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    # mtime=0 keeps the bytes stable across rebuilds of identical data, so an
    # unchanged feed produces no commit and no needless extension re-download.
    with gzip.GzipFile(filename="", mode="wb", fileobj=open(path, "wb"), mtime=0) as handle:
        handle.write(raw)

    compressed = path.read_bytes()
    return {
        "bytes": len(compressed),
        "raw_bytes": len(raw),
        "sha256": hashlib.sha256(compressed).hexdigest(),
    }


def build(season: str, out_dir: Path, tail_days: int, today: date) -> Dict[str, object]:
    """Write every feed file for ``season`` into ``out_dir`` and return the manifest."""
    out_dir.mkdir(parents=True, exist_ok=True)

    projections = build_projections(season)
    players = build_players(season, tail_days, today)
    schedule = build_schedule(season)
    index = build_player_index(projections)

    prev = previous_season(season)
    prev_players = build_players(prev, tail_days=0, today=today)

    files = {
        "projections.json.gz": _write_gzip(out_dir / "projections.json.gz", projections),
        "players.json.gz": _write_gzip(out_dir / "players.json.gz", players),
        "players-prev.json.gz": _write_gzip(out_dir / "players-prev.json.gz", prev_players),
        "schedule.json.gz": _write_gzip(out_dir / "schedule.json.gz", schedule),
        "player-index.json.gz": _write_gzip(out_dir / "player-index.json.gz", index),
    }

    meta = {
        "schema": SCHEMA_VERSION,
        "season": season,
        "previous_season": prev,
        "generated_at": datetime.now().astimezone().isoformat(),
        "counts": {
            "projected_players": projections["count"],
            "players_with_games": players["count"],
            "previous_season_players": prev_players["count"],
            "scheduled_games": schedule["game_count"],
            "mapped_yahoo_ids": index["count"],
            "mapped_names": index["name_count"],
        },
        "files": files,
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return meta


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "season",
        help=f"NBA season to build, e.g. {get_current_season()}",
    )
    parser.add_argument(
        "--out",
        default="feed",
        help="Directory to write the feed into (default: feed/)",
    )
    parser.add_argument(
        "--tail-days",
        type=int,
        default=35,
        help="Days of game log to carry, enough for last30d plus staleness (default: 35)",
    )
    parser.add_argument(
        "--today",
        default=None,
        help=(
            "Anchor date (YYYY-MM-DD): the feed sees only games up to it, in the season "
            "averages and the game-log tail. Defaults to today; set it to rebuild a "
            "historical feed for test fixtures or backtests."
        ),
    )
    args = parser.parse_args(argv)

    anchor = date.fromisoformat(args.today) if args.today else date.today()
    meta = build(args.season, Path(args.out), args.tail_days, anchor)

    print(f"feed for {meta['season']} -> {args.out}/")
    for name, info in meta["files"].items():
        print(f"  {name:<24} {info['bytes'] / 1024:7.1f} KB gz  ({info['raw_bytes'] / 1024:8.1f} KB raw)")
    for label, value in meta["counts"].items():
        print(f"  {label:<24} {value}")

    if not meta["counts"]["scheduled_games"]:
        # Games-remaining is the extension's headline overlay and it is pure schedule
        # math, so an empty schedule makes the feed useless rather than merely thin.
        # An empty game log, by contrast, is the normal preseason state.
        print(
            f"\nERROR: no cached schedule for {args.season}. "
            "Run the schedule refresh before building the feed:\n"
            "  pipenv run python -c \"from tools.schedule import schedule_refresh; "
            f"schedule_refresh.cache_all_team_schedules('{args.season}')\"",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
