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


#: Per-game lines chosen to stress the valuation: a rim-protecting big who can't shoot free
#: throws, a high-volume guard, an efficient player on almost no attempts, a player with no
#: free-throw attempts at all, and two players ranked outside the reference pool.
VALUATION_PLAYERS = [
    # id, fgm, fga, ftm, fta, threes, pts, reb, ast, stl, blk, to
    ("v.1", 9.8, 16.0, 3.1, 5.6, 0.2, 22.9, 12.1, 2.4, 0.9, 2.6, 2.1),
    ("v.2", 9.4, 21.0, 7.2, 8.0, 3.6, 29.6, 4.8, 7.9, 1.4, 0.4, 3.6),
    ("v.3", 1.2, 2.0, 0.3, 0.4, 0.0, 2.7, 2.2, 0.4, 0.2, 0.3, 0.3),
    ("v.4", 4.1, 9.3, 0.0, 0.0, 2.1, 10.3, 3.1, 1.6, 0.8, 0.2, 0.9),
    ("v.5", 6.8, 15.2, 4.4, 5.0, 2.9, 20.9, 5.6, 5.1, 1.7, 0.6, 2.4),
    ("v.6", 5.2, 10.1, 2.0, 2.9, 0.4, 12.8, 8.7, 1.9, 0.7, 1.4, 1.2),
    ("v.7", 3.6, 8.8, 1.9, 2.2, 2.4, 11.5, 2.9, 4.4, 1.1, 0.3, 1.5),
    ("v.8", 7.7, 17.9, 5.3, 6.1, 1.8, 22.5, 6.0, 3.3, 1.0, 0.5, 2.8),
    ("v.9", 2.9, 5.4, 1.1, 1.9, 0.1, 6.9, 6.4, 0.9, 0.5, 1.8, 0.8),
    ("v.10", 4.6, 11.0, 2.6, 3.0, 2.7, 14.5, 3.4, 6.2, 1.3, 0.4, 2.0),
    ("v.11", 2.2, 5.1, 0.9, 1.2, 1.0, 6.3, 2.1, 1.2, 0.4, 0.1, 0.6),
    ("v.12", 1.9, 4.8, 0.4, 0.9, 1.1, 5.3, 1.9, 0.8, 0.3, 0.2, 0.5),
]

#: Players ranked past this are valued but not part of the reference pool.
VALUATION_POOL_SIZE = 10


@pytest.mark.unit
def test_write_valuation_fixture():
    """Category z-scores from ``value_model``, for the TS port to match.

    The trade insights value every rostered player with this, so a drift here would move
    every team's strengths at once.
    """
    from tools.draft import stat_ids, value_model
    from tools.draft.draft_state import DraftPlayer

    categories = stat_ids.parse_stat_categories(STAT_META)
    ids_by_name = {category.name: str(category.stat_id) for category in categories}

    players = []
    for rank, (player_id, fgm, fga, ftm, fta, threes, pts, reb, ast, stl, blk, tov) in enumerate(
        VALUATION_PLAYERS, start=1
    ):
        line = {
            "games_played": 70.0,
            "fgm": fgm, "fga": fga, "fg_pct": fgm / fga if fga else 0.0,
            "ftm": ftm, "fta": fta, "ft_pct": ftm / fta if fta else 0.0,
            "threes": threes, "points": pts, "rebounds": reb, "assists": ast,
            "steals": stl, "blocks": blk, "turnovers": tov,
        }
        players.append(
            DraftPlayer(player_id=player_id, first_name=player_id, last_name="",
                        projected_rank=rank, projected=line)
        )

    context = value_model.build_context(players, categories, VALUATION_POOL_SIZE)
    pool = value_model.select_reference_pool(players, VALUATION_POOL_SIZE)
    punt = {"turnovers", "ft_pct"}

    cases = []
    for player in players:
        valued = value_model.value_player(player, context)
        cases.append({
            "id": player.player_id,
            "line": {key: value for key, value in player.projected.items() if key != "games_played"},
            "expected": {
                "z": {ids_by_name[name]: z for name, z in valued.category_z.items()},
                "total": valued.total(),
                "totalPunting": valued.total(punt),
            },
        })

    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    (FIXTURE_DIR / "valuation.json").write_text(
        json.dumps(
            {
                "statMeta": STAT_META,
                "pool": [player.player_id for player in pool],
                "punt": sorted(ids_by_name[name] for name in punt),
                "context": {
                    "ratioBaselines": {ids_by_name[k]: v for k, v in context.ratio_baselines.items()},
                    "means": {ids_by_name[k]: v for k, v in context.means.items()},
                    "stddevs": {ids_by_name[k]: v for k, v in context.stddevs.items()},
                },
                "cases": cases,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    # The fixture must exercise what it claims: players outside the pool, a player with no
    # free throws, and turnovers inverted so fewer is worth more.
    assert len(pool) == VALUATION_POOL_SIZE < len(players)
    by_id = {case["id"]: case["expected"]["z"] for case in cases}
    assert by_id["v.4"][ids_by_name["ft_pct"]] == pytest.approx(
        -context.means["ft_pct"] / context.stddevs["ft_pct"]
    )
    assert by_id["v.3"][ids_by_name["turnovers"]] > 0 > by_id["v.2"][ids_by_name["turnovers"]]


#: The web app's waiver lookbacks that the extension's form table offers from the game tail.
FORM_MODES = ("last", "last3", "last7", "last7d", "last14d", "last30d")


def _window_stats(stats) -> Dict[str, float]:
    return {
        "fgm": stats.fgm, "fga": stats.fga, "fg_pct": stats.fg_pct,
        "ftm": stats.ftm, "fta": stats.fta, "ft_pct": stats.ft_pct,
        "threes": stats.threes, "points": stats.points, "rebounds": stats.rebounds,
        "assists": stats.assists, "steals": stats.steals, "blocks": stats.blocks,
        "turnovers": stats.turnovers,
    }


@pytest.mark.unit
def test_write_stat_window_fixture(monkeypatch):  # pylint: disable=too-many-locals
    """Real game logs plus Python's per-game averages for every projection mode.

    This is the check that matters most for day-to-day numbers: the extension recomputes
    last3/last7/last7d/last30d in the browser from the same game rows the feed ships, and
    it has to land on the same averages ``compute_player_stats`` produces. The ``form``
    block adds the rest of the web app's waiver lookbacks, summed as well as averaged,
    with minutes and the minute trend.
    """
    from datetime import date, timedelta

    from scripts.build_feed import GAME_FIELDS, _compact_game
    from tools.boxscore import boxscore_cache
    from tools.player import player_fetcher
    from tools.player.player_minutes_trend import compute_minute_trend
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

    # Box scores list games a player sat with blank minutes, and Python counts them as
    # games. Make sure one case has such a game inside the 14-day window.
    recent_cutoff = (anchor - timedelta(days=14)).isoformat()
    sat_recently = next(
        (
            entry for entry in candidates[5:]
            if any(g.get("MIN") in ("", None) and str(g.get("date")) >= recent_cutoff for g in entry[2])
        ),
        None,
    )
    candidates = candidates[:5] + ([sat_recently] if sat_recently else [])

    if not candidates:
        pytest.skip("no player has enough cached games before the anchor date")

    original_fetch = player_fetcher.fetch_player_stats_from_cache

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
            expected[mode] = _window_stats(stats)

        form: Dict[str, Dict[str, Dict[str, float]]] = {"avg": {}, "sum": {}}
        for agg_mode, by_mode in form.items():
            for mode in FORM_MODES:
                stats = compute_player_stats(
                    player_id=player_id, season=season, mode=mode,
                    season_start=season_start, today=anchor, agg_mode=agg_mode,
                )
                if stats is not None:
                    by_mode[mode] = {**_window_stats(stats), "minutes": stats.minutes, "games": stats.games_count}

        # The trend reads the current season up to date.today(); pin it to the fixture's
        # season and anchor so it is the trend the web app showed on that day.
        with monkeypatch.context() as patch:
            patch.setattr(
                player_fetcher, "fetch_player_stats_from_cache",
                lambda pid, _season, _start, _end: original_fetch(pid, season, season_start, anchor),
            )
            last, prior, delta, _ = compute_minute_trend(player_id, "Regular Season")
        trend = {"last": last, "priorAverage": prior, "delta": delta}

        cases.append({
            "nbaId": str(player_id), "name": player_name, "games": rows,
            "expected": expected, "form": form, "trend": trend,
        })

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
    assert all(case["form"]["avg"].get("last") for case in cases)


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
