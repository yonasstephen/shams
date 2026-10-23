"""Tests for the nightly feed job: scheduling, retries and healing gaps in the cache."""

from __future__ import annotations

import copy
from datetime import datetime, time as clock, timedelta

import pytest

from scripts import nightly_feed
from scripts.nightly_feed import EASTERN, next_run, run_with_retries
from scripts.publish_feed import PublishError
from tools.boxscore import boxscore_cache, boxscore_fetcher, boxscore_refresh
from tools.schedule import schedule_cache, schedule_refresh


def _eastern(*args: int) -> datetime:
    return EASTERN.localize(datetime(*args))


@pytest.mark.unit
def test_next_run_is_today_until_the_hour_passes_then_tomorrow():
    at = clock(5, 0)
    assert next_run(_eastern(2026, 10, 23, 4, 0), at) == _eastern(2026, 10, 23, 5, 0)
    assert next_run(_eastern(2026, 10, 23, 5, 0), at) == _eastern(2026, 10, 24, 5, 0)


@pytest.mark.unit
def test_next_run_keeps_the_wall_clock_across_the_dst_change():
    # Clocks fall back at 02:00 on 2026-11-01: 05:00 that morning is EST, not EDT.
    run = next_run(_eastern(2026, 11, 1, 0, 30), clock(5, 0))
    assert (run.hour, run.utcoffset()) == (5, timedelta(hours=-5))


@pytest.fixture(name="quiet")
def fixture_quiet(monkeypatch):
    monkeypatch.setattr(nightly_feed, "log", lambda message: None)


@pytest.mark.unit
@pytest.mark.usefixtures("quiet")
def test_a_failing_run_is_retried_an_hour_later():
    outcomes = [RuntimeError("stats.nba.com timed out"), RuntimeError("again"), "published"]
    sleeps = []

    def job():
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    assert run_with_retries(job, attempts=3, sleep=sleeps.append)
    assert sleeps == [3600, 3600]


@pytest.mark.unit
@pytest.mark.usefixtures("quiet")
def test_a_refused_build_is_not_retried():
    sleeps = []

    def job():
        raise PublishError("projected_players would drop to 0")

    assert not run_with_retries(job, attempts=3, sleep=sleeps.append)
    assert not sleeps


@pytest.mark.unit
@pytest.mark.usefixtures("quiet")
def test_a_one_off_run_gives_up_without_waiting():
    sleeps = []

    def job():
        raise RuntimeError("no network")

    assert not run_with_retries(job, attempts=1, sleep=sleeps.append)
    assert not sleeps


@pytest.mark.unit
def test_full_season_fetches_start_on_october_first():
    # 2021-22 tipped off October 19: a walk from October 21 would skip opening night.
    assert boxscore_refresh.get_season_start_date("2021-22").isoformat() == "2021-10-01"


@pytest.mark.unit
def test_missing_opening_night_is_found_and_fetched(temp_cache_dir, sample_game_data, monkeypatch):
    """A cache that began after the opener heals: the opener is detected and fetched."""
    season = "2021-22"
    opener, preseason = "0022100001", "0012100016"
    monkeypatch.setattr(boxscore_cache, "get_cache_dir", lambda: temp_cache_dir)
    monkeypatch.setattr(schedule_cache, "get_cache_dir", lambda: temp_cache_dir / "schedules")
    (temp_cache_dir / "schedules").mkdir()

    schedule_cache.save_full_schedule(
        season,
        {
            "season": season,
            "date_games": {
                "2021-10-04": [{"game_id": preseason, "game_datetime": "2021-10-04T19:00:00Z"}],
                "2021-10-19": [
                    {
                        "game_id": opener,
                        "game_datetime": "2021-10-19T19:30:00Z",
                        "postponed_status": "N",
                        "home_team_tricode": "MIL",
                        "away_team_tricode": "BKN",
                    }
                ],
            },
            "game_times": {opener: "2021-10-19T19:30:00Z", preseason: "2021-10-04T19:00:00Z"},
        },
    )
    monkeypatch.setattr(
        schedule_refresh,
        "cache_all_team_schedules",
        lambda _season: (
            {"2021-10-04": [preseason], "2021-10-19": [opener]},
            {opener: "2021-10-19T19:30:00Z", preseason: "2021-10-04T19:00:00Z"},
        ),
    )

    requested = []

    def fetch_box_score(game_id, game_date=None):
        requested.append((game_id, game_date))
        game = copy.deepcopy(sample_game_data)
        game["game_id"] = game_id
        return game, None

    monkeypatch.setattr(boxscore_fetcher, "fetch_box_score", fetch_box_score)

    assert list(boxscore_cache.detect_missing_games(season)) == ["2021-10-19"]

    summary = boxscore_refresh.fill_missing_games(season)

    assert summary["dates"] == ["2021-10-19"]
    assert summary["games_fetched"] == 1
    assert requested == [(opener, "2021-10-19")]  # never the preseason game
    assert boxscore_cache.load_game(opener, season) is not None
    assert boxscore_cache.load_player_season_stats(203507, season)["games_played"] == 1
    assert not boxscore_cache.detect_missing_games(season)
    assert boxscore_refresh.fill_missing_games(season)["dates"] == []
