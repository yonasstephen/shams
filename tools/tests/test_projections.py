"""Tests for the offline projection engine."""

from __future__ import annotations

import pytest

from tools.projections import backtest, history, marcel
from tools.projections.history import SeasonLine


def season_line(
    nba_id: int,
    season: str,
    games: int,
    mpg: float,
    per36_points: float = 20.0,
    **totals,
) -> SeasonLine:
    """Build a season line from per-36 intent rather than raw totals."""
    minutes = games * mpg
    line = SeasonLine(
        nba_id=nba_id,
        name=f"P{nba_id}",
        season=season,
        games_played=games,
        minutes=minutes,
        totals={stat: 0.0 for stat in marcel.RATE_STATS},
    )
    line.totals["points"] = per36_points * minutes / 36.0
    for stat, per36 in totals.items():
        line.totals[stat] = per36 * minutes / 36.0
    return line


class TestMinuteParsing:
    """Yahoo/NBA send minutes as MM:SS."""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("14:58", 14 + 58 / 60),
            ("0:30", 0.5),
            ("36", 36.0),
            (28.5, 28.5),
            ("", 0.0),
            (None, 0.0),
            ("junk", 0.0),
        ],
    )
    def test_parses(self, raw, expected):
        assert history.parse_minutes(raw) == pytest.approx(expected)


class TestSeasonLine:
    """Derived quantities off the raw totals."""

    def test_per_36_scales_by_minutes(self):
        line = season_line(1, "2024-25", games=70, mpg=36.0, per36_points=25.0)
        assert line.per_36("points") == pytest.approx(25.0)

    def test_per_36_suppressed_below_the_minutes_floor(self):
        """A handful of minutes produces a meaningless rate."""
        line = season_line(1, "2024-25", games=2, mpg=5.0, per36_points=60.0)
        assert line.minutes < history.MIN_MINUTES_FOR_RATES
        assert line.per_36("points") == 0.0

    def test_percentages_come_from_makes_over_attempts(self):
        line = season_line(1, "2024-25", games=70, mpg=36.0, fgm=9.0, fga=18.0)
        assert line.fg_pct == pytest.approx(0.5)

    def test_percentage_with_no_attempts_is_zero(self):
        line = season_line(1, "2024-25", games=70, mpg=36.0)
        assert line.fg_pct == 0.0
        assert line.ft_pct == 0.0

    def test_team_changes_detected(self):
        line = season_line(1, "2024-25", games=70, mpg=30.0)
        line.team_ids = [1610612747] * 40 + [1610612738] * 30
        assert line.changed_teams is True
        assert line.primary_team_id == 1610612747

    def test_single_team_is_not_a_change(self):
        line = season_line(1, "2024-25", games=70, mpg=30.0)
        line.team_ids = [1610612747] * 70
        assert line.changed_teams is False


class TestMarcelProjection:
    """The baseline model."""

    def _rates(self):
        pool = [
            season_line(i, "2024-25", games=70, mpg=30.0, per36_points=20.0)
            for i in range(100, 140)
        ]
        return marcel.league_rates(pool)

    def test_recent_seasons_weigh_more(self):
        """A player improving year over year should project above his average."""
        rates = self._rates()
        improving = [
            season_line(1, "2024-25", games=70, mpg=34.0, per36_points=30.0),
            season_line(1, "2023-24", games=70, mpg=34.0, per36_points=20.0),
        ]
        declining = [
            season_line(2, "2024-25", games=70, mpg=34.0, per36_points=20.0),
            season_line(2, "2023-24", games=70, mpg=34.0, per36_points=30.0),
        ]
        up = marcel.project_player(improving, rates)
        down = marcel.project_player(declining, rates)
        assert up.per_game["points"] > down.per_game["points"]

    def test_small_samples_regress_toward_the_league(self):
        """A hot 100-minute stretch must not project as a superstar."""
        rates = self._rates()
        elite_tiny = marcel.project_player(
            [season_line(1, "2024-25", games=5, mpg=20.0, per36_points=45.0)], rates
        )
        elite_full = marcel.project_player(
            [season_line(2, "2024-25", games=75, mpg=36.0, per36_points=45.0)], rates
        )
        tiny_per36 = elite_tiny.per_game["points"] * 36.0 / elite_tiny.minutes_per_game
        full_per36 = elite_full.per_game["points"] * 36.0 / elite_full.minutes_per_game
        assert tiny_per36 < full_per36

    def test_no_history_projects_nothing(self):
        assert marcel.project_player([], self._rates()) is None

    def test_zero_minute_history_projects_nothing(self):
        line = season_line(1, "2024-25", games=0, mpg=0.0)
        assert marcel.project_player([line], self._rates()) is None

    def test_totals_recompute_percentages(self):
        rates = self._rates()
        line = marcel.project_player(
            [season_line(1, "2024-25", games=70, mpg=34.0, fgm=9.0, fga=18.0)], rates
        )
        totals = line.totals()
        assert totals["fg_pct"] == pytest.approx(totals["fgm"] / totals["fga"])
        assert totals["games_played"] == pytest.approx(line.games)

    def test_experience_lifts_young_players(self):
        rates = self._rates()
        history_ = [season_line(1, "2024-25", games=70, mpg=24.0)]
        rookie = marcel.project_player(history_, rates, experience=0)
        prime = marcel.project_player(history_, rates, experience=6)
        old = marcel.project_player(history_, rates, experience=15)
        assert rookie.minutes_per_game > prime.minutes_per_game > old.minutes_per_game

    def test_projected_games_are_capped_at_a_season(self):
        rates = self._rates()
        line = marcel.project_player(
            [season_line(1, "2024-25", games=82, mpg=38.0)], rates, experience=0
        )
        assert line.games <= 82.0

    def test_project_season_skips_players_without_history(self):
        seasons = {
            "2024-25": {1: season_line(1, "2024-25", games=70, mpg=30.0)},
            "2023-24": {2: season_line(2, "2023-24", games=0, mpg=0.0)},
        }
        result = marcel.project_season(seasons, ["2024-25", "2023-24"])
        assert 1 in result

    def test_project_season_with_no_known_seasons_is_empty(self):
        assert not marcel.project_season({}, ["2024-25"])


class TestBacktestMetrics:
    """The gate's own arithmetic."""

    def test_spearman_perfect_agreement(self):
        pairs = [(1.0, 10.0), (2.0, 20.0), (3.0, 30.0), (4.0, 40.0)]
        assert backtest._spearman(pairs) == pytest.approx(1.0)

    def test_spearman_perfect_inversion(self):
        pairs = [(1.0, 40.0), (2.0, 30.0), (3.0, 20.0), (4.0, 10.0)]
        assert backtest._spearman(pairs) == pytest.approx(-1.0)

    def test_spearman_handles_ties(self):
        pairs = [(1.0, 5.0), (1.0, 5.0), (2.0, 9.0), (3.0, 12.0)]
        assert -1.0 <= backtest._spearman(pairs) <= 1.0

    def test_spearman_needs_a_sample(self):
        assert backtest._spearman([(1.0, 2.0)]) == 0.0

    def test_evaluate_ignores_low_minute_players(self):
        actuals = {
            1: season_line(1, "2025-26", games=70, mpg=30.0, per36_points=20.0),
            2: season_line(2, "2025-26", games=3, mpg=5.0, per36_points=20.0),
        }
        predictions = {1: {"points": 15.0}, 2: {"points": 15.0}}
        metrics = backtest.evaluate(predictions, actuals, label="t")
        assert metrics.players == 1

    def test_evaluate_with_no_overlap_is_empty(self):
        metrics = backtest.evaluate({}, {}, label="t")
        assert metrics.players == 0
        assert metrics.mean_mae == 0.0

    def test_perfect_prediction_has_zero_error(self):
        actual = season_line(1, "2025-26", games=70, mpg=30.0, per36_points=24.0)
        predictions = {1: {stat: actual.per_game(stat) for stat in backtest.COMPARED}}
        metrics = backtest.evaluate(predictions, {1: actual}, label="oracle")
        assert metrics.mean_mae == pytest.approx(0.0)

    def test_test_season_cannot_be_a_prior(self):
        with pytest.raises(ValueError, match="both training and test"):
            backtest.run("2025-26", ["2025-26"])


class TestBackfillCompleteness:
    """Guard against silently modelling on an incomplete cache."""

    @pytest.mark.parametrize(
        "game_id,expected",
        [
            ("0022300001", True),   # regular season
            ("0012300001", False),  # preseason
            ("0042300001", False),  # playoffs
            ("", False),
            (None, False),
            ("12", False),
        ],
    )
    def test_game_type_from_id(self, game_id, expected):
        from scripts.build_projections import is_regular_season

        assert is_regular_season(game_id) is expected
