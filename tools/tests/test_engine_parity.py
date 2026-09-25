"""Generate and check the parity fixtures shared with the TypeScript engine.

The season Chrome extension reimplements the projection math in TypeScript so it can run
without a server. Two implementations drift unless something forces them together: this
module is that something. It writes the scenarios and Python's answers to
``extension-season/test/fixtures/``, and ``npm test`` over there asserts the TypeScript
engine produces the same numbers.

Regenerate after any change to the projection math:

    cd tools/tests && pipenv run pytest test_engine_parity.py -v
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

import pytest

from tools.matchup import matchup_projection, roster_optimizer

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "extension-season" / "test" / "fixtures"

#: A 9-category league as Yahoo describes one. sort_order "0" means lower is better.
STAT_META: List[Dict[str, object]] = [
    {"stat_id": "5", "display_name": "FG%", "name": "Field Goal Percentage", "sort_order": "1"},
    {"stat_id": "8", "display_name": "FT%", "name": "Free Throw Percentage", "sort_order": "1"},
    {"stat_id": "10", "display_name": "3PTM", "name": "3-point Shots Made", "sort_order": "1"},
    {"stat_id": "12", "display_name": "PTS", "name": "Points Scored", "sort_order": "1"},
    {"stat_id": "15", "display_name": "REB", "name": "Total Rebounds", "sort_order": "1"},
    {"stat_id": "16", "display_name": "AST", "name": "Assists", "sort_order": "1"},
    {"stat_id": "17", "display_name": "ST", "name": "Steals", "sort_order": "1"},
    {"stat_id": "18", "display_name": "BLK", "name": "Blocked Shots", "sort_order": "1"},
    {"stat_id": "19", "display_name": "TO", "name": "Turnovers", "sort_order": "0"},
    {"stat_id": "9004003", "display_name": "FGM/A", "name": "FGM/A", "sort_order": "1", "is_only_display_stat": 1},
]


def _totals(fgm, fga, ftm, fta, threes, pts, reb, ast, stl, blk, to) -> Dict[str, float]:
    return {
        "5": fgm / fga if fga else 0.0,
        "8": ftm / fta if fta else 0.0,
        "10": threes, "12": pts, "15": reb, "16": ast, "17": stl, "18": blk, "19": to,
        "_FGM": fgm, "_FGA": fga, "_FTM": ftm, "_FTA": fta,
    }


#: Ordinary win, percentage tie broken on volume, exact tie, and a turnovers flip.
POINT_SCENARIOS = [
    {
        "name": "clear-win",
        "a": _totals(320, 700, 120, 150, 55, 820, 310, 180, 40, 25, 95),
        "b": _totals(290, 690, 140, 170, 48, 780, 330, 165, 45, 30, 88),
    },
    {
        "name": "percentage-tie-volume-breaks-it",
        "a": _totals(300, 600, 100, 125, 50, 800, 300, 170, 42, 28, 90),
        "b": _totals(150, 300, 80, 100, 50, 800, 300, 170, 42, 28, 90),
    },
    {
        "name": "exact-tie",
        "a": _totals(300, 600, 100, 125, 50, 800, 300, 170, 42, 28, 90),
        "b": _totals(300, 600, 100, 125, 50, 800, 300, 170, 42, 28, 90),
    },
    {
        "name": "turnovers-lower-is-better",
        "a": _totals(300, 640, 110, 140, 52, 790, 305, 175, 41, 26, 70),
        "b": _totals(300, 640, 110, 140, 52, 790, 305, 175, 41, 26, 120),
    },
]

#: Slot pressure: flexible and inflexible players competing for the same slots.
OPTIMIZER_SCENARIOS = [
    {
        "name": "centers-crowd-out-util",
        "players": [
            {"player_key": "p.1", "eligible_positions": ["C"]},
            {"player_key": "p.2", "eligible_positions": ["C"]},
            {"player_key": "p.3", "eligible_positions": ["PG", "SG"]},
            {"player_key": "p.4", "eligible_positions": ["SF", "PF"]},
            {"player_key": "p.5", "eligible_positions": ["PG"]},
        ],
        "roster_positions": ["PG", "SG", "G", "SF", "PF", "F", "C", "Util", "BN", "BN"],
        "with_games": ["p.1", "p.2", "p.3", "p.4", "p.5"],
        "ranks": {"p.1": 10, "p.2": 40, "p.3": 5, "p.4": 22, "p.5": 60},
    },
    {
        "name": "no-games-means-bench",
        "players": [
            {"player_key": "p.1", "eligible_positions": ["PG", "SG"]},
            {"player_key": "p.2", "eligible_positions": ["C"]},
        ],
        "roster_positions": ["PG", "C", "Util", "BN"],
        "with_games": ["p.1"],
        "ranks": {},
    },
    {
        "name": "rank-breaks-flexibility-tie",
        "players": [
            {"player_key": "p.a", "eligible_positions": ["SF"]},
            {"player_key": "p.b", "eligible_positions": ["SF"]},
        ],
        "roster_positions": ["SF", "BN"],
        "with_games": ["p.a", "p.b"],
        "ranks": {"p.a": 300, "p.b": 12},
    },
]


@pytest.mark.unit
def test_write_category_scoring_fixture():
    """Python's category W-L-T for each scenario, for the TS engine to match."""
    cases = []
    for scenario in POINT_SCENARIOS:
        points_a, points_b = matchup_projection._calculate_projected_points(
            STAT_META, scenario["a"], scenario["b"]
        )
        cases.append({
            "name": scenario["name"],
            "teamA": scenario["a"],
            "teamB": scenario["b"],
            "expected": {"a": points_a, "b": points_b},
        })

    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"statMeta": STAT_META, "cases": cases}
    (FIXTURE_DIR / "category-scoring.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    # Sanity: the scenarios must actually exercise wins, losses and ties.
    outcomes = {(case["expected"]["a"]["win"], case["expected"]["a"]["tie"]) for case in cases}
    assert len(outcomes) > 1


@pytest.mark.unit
def test_write_roster_optimizer_fixture():
    """Python's greedy slot assignment, for the TS port to match exactly."""
    cases = []
    for scenario in OPTIMIZER_SCENARIOS:
        assignments = roster_optimizer.optimize_roster_positions(
            scenario["players"],
            scenario["roster_positions"],
            set(scenario["with_games"]),
            scenario["ranks"],
        )
        cases.append({**scenario, "expected": assignments})

    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    (FIXTURE_DIR / "roster-optimizer.json").write_text(
        json.dumps({"cases": cases}, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    assert all(case["expected"] for case in cases)


@pytest.mark.unit
def test_write_team_totals_fixture():
    """Summing player lines into a team total, percentages from pooled volume."""
    player_contributions = {
        "p.1": {"5": 0.0, "8": 0.0, "10": 8.0, "12": 96.0, "15": 24.0, "16": 30.0, "17": 6.0, "18": 2.0, "19": 12.0},
        "p.2": {"5": 0.0, "8": 0.0, "10": 2.0, "12": 60.0, "15": 45.0, "16": 9.0, "17": 3.0, "18": 9.0, "19": 8.0},
        "p.3": {"5": 0.0, "8": 0.0, "10": 11.0, "12": 75.0, "15": 15.0, "16": 12.0, "17": 5.0, "18": 1.0, "19": 7.0},
    }
    player_shooting = {
        "p.1": {"fgm": 36.0, "fga": 78.0, "ftm": 16.0, "fta": 18.0},
        "p.2": {"fgm": 26.0, "fga": 44.0, "ftm": 6.0, "fta": 14.0},
        "p.3": {"fgm": 27.0, "fga": 66.0, "ftm": 10.0, "fta": 11.0},
    }

    totals = matchup_projection._sum_player_contributions_to_team_total(
        player_contributions, player_shooting, STAT_META
    )

    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    (FIXTURE_DIR / "team-totals.json").write_text(
        json.dumps(
            {
                "statMeta": STAT_META,
                "playerContributions": player_contributions,
                "playerShooting": player_shooting,
                "expected": totals,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    # Percentages must come from pooled volume, not an average of per-player rates.
    assert totals["5"] == pytest.approx((36 + 26 + 27) / (78 + 44 + 66))
    assert totals["8"] == pytest.approx((16 + 6 + 10) / (18 + 14 + 11))


@pytest.mark.unit
def test_write_stat_window_fixture():
    """Real game logs plus Python's per-game averages for every projection mode.

    This is the check that matters most for day-to-day numbers: the extension recomputes
    last3/last7/last7d/last30d in the browser from the same game rows the feed ships, and
    it has to land on the same averages ``compute_player_stats`` produces.
    """
    from datetime import date

    from scripts.build_feed import GAME_FIELDS, _compact_game
    from tools.boxscore import boxscore_cache
    from tools.player.player_stats import compute_player_stats
    from tools.schedule.schedule_fetcher import get_season_start_date

    season = "2025-26"
    anchor = date(2026, 1, 15)
    season_start = get_season_start_date(season)

    stats_dir = boxscore_cache.get_cache_dir() / "season_stats" / season
    if not stats_dir.exists() or not any(stats_dir.glob("*.json")):
        pytest.skip(f"no cached box scores for {season}; run /refresh to regenerate this fixture")

    players_dir = boxscore_cache.get_cache_dir() / "players" / season
    candidates = []
    for path in sorted(players_dir.glob("*.json")):
        prefix = path.stem.split("_", 1)[0]
        if not prefix.isdigit():
            continue
        cached = boxscore_cache.load_player_games(int(prefix), season) or {}
        games = [g for g in (cached.get("games") or []) if str(g.get("date", "")) <= anchor.isoformat()]
        if len(games) >= 12:
            candidates.append((int(prefix), cached.get("player_name", ""), games))

    # Busiest players first, so the day-based windows land on someone who was actually
    # playing around the anchor date rather than a veteran who had stopped.
    candidates.sort(key=lambda entry: len(entry[2]), reverse=True)
    candidates = candidates[:5]

    if not candidates:
        pytest.skip("no player has enough cached games before the anchor date")

    cases = []
    for player_id, player_name, games in candidates:
        rows = [row for row in (_compact_game(game) for game in games) if row]
        rows.sort(key=lambda row: row[0])

        expected = {}
        for mode in ("season", "last3", "last7", "last7d", "last30d"):
            stats = compute_player_stats(
                player_id=player_id, season=season, mode=mode,
                season_start=season_start, today=anchor, agg_mode="avg",
            )
            if stats is None:
                continue
            expected[mode] = {
                "fgm": stats.fgm, "fga": stats.fga, "fg_pct": stats.fg_pct,
                "ftm": stats.ftm, "fta": stats.fta, "ft_pct": stats.ft_pct,
                "threes": stats.threes, "points": stats.points, "rebounds": stats.rebounds,
                "assists": stats.assists, "steals": stats.steals, "blocks": stats.blocks,
                "turnovers": stats.turnovers,
            }

        cases.append({"nbaId": str(player_id), "name": player_name, "games": rows, "expected": expected})

    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    (FIXTURE_DIR / "stat-windows.json").write_text(
        json.dumps(
            {"season": season, "today": anchor.isoformat(), "fields": list(GAME_FIELDS), "cases": cases},
            indent=2, sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    assert cases and all(case["expected"].get("season") for case in cases)


@pytest.mark.unit
def test_write_name_normalization_fixture():
    """Name normalization, which is how a Yahoo roster row finds its NBA stats.

    The Yahoo id index only covers players a past waiver or ranking run touched, so the
    extension falls back to matching on name exactly as the Python engine does. If the two
    normalizers disagree on an accent or a suffix, that player silently projects as zeros.
    """
    from tools.utils.player_index import normalize_player_name

    names = [
        "James Harden",
        "Nikola Jokić",
        "Luka Dončić",
        "Jaime Jaquez Jr.",
        "Kristaps Porziņģis",
        "Alperen Şengün",
        "Dennis Schröder",
        "  Bogdan Bogdanović  ",
        "Jabari Smith Jr.",
        "P.J. Washington",
        "De'Aaron Fox",
        "Karl-Anthony Towns",
        "Nicolas Claxton",
    ]

    cases = [{"input": name, "expected": normalize_player_name(name)} for name in names]

    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    (FIXTURE_DIR / "name-normalization.json").write_text(
        json.dumps({"cases": cases}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    # The accented names must actually lose their accents, or the fixture proves nothing.
    assert dict(zip(names, (case["expected"] for case in cases)))["Nikola Jokić"] == "nikola jokic"
