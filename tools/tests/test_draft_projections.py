"""Tests for projection sources and the CSV export layer."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.draft import projections
from tools.draft.draft_state import DraftPlayer
from tools.projections import export
from tools.projections.marcel import ProjectedLine


def draft_player(pid: str, name: str, projected=None, injury: str = "") -> DraftPlayer:
    """A pool player with an optional Yahoo projected line."""
    return DraftPlayer(
        player_id=pid,
        first_name=name.split()[0],
        last_name=" ".join(name.split()[1:]),
        injury=injury,
        projected=projected or {},
    )


def csv_row(name: str, yahoo_id: str = "", gp: float = 70.0, **per_game):
    """A CSV row as read back off disk."""
    row = {
        "nba_id": "1",
        "yahoo_id": yahoo_id,
        "name": name,
        "team": "LAL",
        "positions": "",
        "gp": gp,
        "mpg": 32.0,
        "source": "marcel",
        "confidence": 0.9,
    }
    for stat in export.STAT_COLUMNS:
        row[stat] = per_game.get(stat, 1.0)
    return row


class TestNameNormalization:
    """Names are the fallback when a Yahoo id is missing."""

    @pytest.mark.parametrize(
        "left,right",
        [
            ("Nikola Jokić", "Nikola Jokic"),
            ("Luka Dončić", "Luka Doncic"),
            ("Jaren Jackson Jr.", "Jaren Jackson"),
            ("Gary Trent Jr", "Gary Trent"),
            ("Royce O'Neale", "Royce ONeale"),
            ("Shai Gilgeous-Alexander", "Shai Gilgeous Alexander"),
            ("Jimmy Butler III", "Jimmy Butler"),
        ],
    )
    def test_equivalent_spellings_match(self, left, right):
        assert projections._normalize(left) == projections._normalize(right)

    def test_different_players_do_not_collide(self):
        assert projections._normalize("Jalen Green") != projections._normalize("Jeff Green")


class TestYahooStoreSource:
    """The default source."""

    def test_passes_through_a_real_line(self):
        player = draft_player("1", "A B", {"games_played": 70.0, "points": 1400.0})
        line = projections.YahooStoreSource().line_for(player)
        assert line["points"] == 1400.0

    def test_empty_line_reads_as_missing(self):
        player = draft_player("1", "A B", {"games_played": 0.0, "points": 0.0})
        assert projections.YahooStoreSource().line_for(player) is None


class TestCsvSource:
    """Our model's export."""

    def test_matches_by_yahoo_id(self):
        source = projections.CsvSource([csv_row("Someone Else", yahoo_id="42", points=20.0)])
        player = draft_player("42", "Name Mismatch")
        line = source.line_for(player)
        assert line["points"] == pytest.approx(20.0 * 70)

    def test_matches_by_name_when_no_id(self):
        source = projections.CsvSource([csv_row("Nikola Jokic", points=25.0)])
        player = draft_player("999", "Nikola Jokić")
        assert source.line_for(player) is not None

    def test_converts_per_game_to_totals(self):
        source = projections.CsvSource([csv_row("A B", gp=60.0, points=20.0)])
        line = source.line_for(draft_player("1", "A B"))
        assert line["games_played"] == 60.0
        assert line["points"] == pytest.approx(1200.0)

    def test_recomputes_percentages_from_volume(self):
        """A hand-edited volume change must not leave a stale ratio."""
        source = projections.CsvSource([csv_row("A B", gp=70.0, fgm=5.0, fga=10.0)])
        line = source.line_for(draft_player("1", "A B"))
        assert line["fg_pct"] == pytest.approx(0.5)

    def test_unknown_player_returns_nothing(self):
        source = projections.CsvSource([csv_row("A B")])
        assert source.line_for(draft_player("1", "Someone Unknown")) is None

    def test_zero_games_is_not_a_projection(self):
        source = projections.CsvSource([csv_row("A B", gp=0.0)])
        assert source.line_for(draft_player("1", "A B")) is None


class TestApplySource:
    """Swapping projections into the pool."""

    def test_csv_overwrites_yahoo(self):
        players = {"1": draft_player("1", "A B", {"games_played": 70.0, "points": 700.0})}
        source = projections.CsvSource([csv_row("A B", gp=70.0, points=20.0)])
        applied = projections.apply_source(players, source)
        assert applied == 1
        assert players["1"].projected["points"] == pytest.approx(1400.0)

    def test_unknown_players_keep_their_yahoo_line(self):
        players = {"1": draft_player("1", "A B", {"games_played": 70.0, "points": 700.0})}
        source = projections.CsvSource([csv_row("Someone Else")])
        assert projections.apply_source(players, source) == 0
        assert players["1"].projected["points"] == 700.0

    def test_inactive_players_are_not_resurrected(self):
        """A retired player has history, so the model happily projects him."""
        retired = draft_player("1", "Jeff Green", {"games_played": 0.0}, injury="NA")
        players = {"1": retired}
        source = projections.CsvSource([csv_row("Jeff Green", gp=60.0, points=10.0)])
        projections.apply_source(players, source)
        assert retired.has_projection is False

    def test_merely_injured_players_still_get_projections(self):
        """GTD is not the same as out of the league."""
        player = draft_player("1", "A B", {"games_played": 70.0, "points": 700.0}, injury="GTD")
        projections.apply_source({"1": player}, projections.CsvSource([csv_row("A B", points=20.0)]))
        assert player.projected["points"] == pytest.approx(1400.0)

    def test_yahoo_source_counts_without_mutating(self):
        players = {
            "1": draft_player("1", "A B", {"games_played": 70.0, "points": 700.0}),
            "2": draft_player("2", "C D", {}),
        }
        assert projections.apply_source(players, projections.YahooStoreSource()) == 1


class TestExportRoundTrip:
    """The CSV is the seam; it has to survive a round trip."""

    def _line(self) -> ProjectedLine:
        line = ProjectedLine(nba_id=1, name="A B", games=70.0, minutes_per_game=32.0)
        line.per_game = {
            "fgm": 8.0, "fga": 16.0, "ftm": 4.0, "fta": 5.0, "threes": 2.0,
            "points": 22.0, "rebounds": 6.0, "assists": 4.0,
            "steals": 1.2, "blocks": 0.8, "turnovers": 2.5,
        }
        line.seasons_used = ["2025-26", "2024-25", "2023-24"]
        return line

    def test_write_then_read(self, tmp_path: Path):
        path = tmp_path / "p.csv"
        rows = export.build_rows({1: self._line()}, teams={1: "LAL"})
        assert export.write_csv(rows, path) == 1

        back = export.read_csv(path)
        assert back[0]["name"] == "A B"
        assert back[0]["points"] == pytest.approx(22.0)
        assert back[0]["fg_pct"] == pytest.approx(0.5)

    def test_missing_file_reads_empty(self, tmp_path: Path):
        assert not export.read_csv(tmp_path / "nope.csv")

    def test_confidence_rises_with_evidence(self):
        thin = ProjectedLine(nba_id=1, name="A", games=40, minutes_per_game=10.0)
        thin.seasons_used = ["2025-26"]
        thick = ProjectedLine(nba_id=2, name="B", games=75, minutes_per_game=34.0)
        thick.seasons_used = ["2025-26", "2024-25", "2023-24"]
        assert export._confidence(thick) > export._confidence(thin)


class TestOverrides:
    """The human escape hatch for rookies and role changes."""

    def _rows(self):
        return [
            {"nba_id": "1", "name": "A B", "gp": 70.0, "mpg": 30.0, "points": 20.0,
             "fgm": 8.0, "fga": 16.0, "ftm": 2.0, "fta": 3.0, "source": "marcel"},
        ]

    def test_override_by_id_replaces_only_filled_columns(self):
        merged = export.apply_overrides(
            self._rows(), [{"nba_id": "1", "name": "", "mpg": 36.0, "points": ""}]
        )
        assert merged[0]["mpg"] == 36.0
        assert merged[0]["points"] == 20.0

    def test_override_by_name_when_id_missing(self):
        merged = export.apply_overrides(self._rows(), [{"nba_id": "", "name": "A B", "mpg": 12.0}])
        assert merged[0]["mpg"] == 12.0

    def test_override_marks_the_source(self):
        merged = export.apply_overrides(self._rows(), [{"nba_id": "1", "mpg": 36.0}])
        assert "override" in merged[0]["source"]

    def test_unmatched_override_is_appended(self):
        """This is how a rookie with no history gets into the file."""
        merged = export.apply_overrides(
            self._rows(), [{"nba_id": "99", "name": "Rookie X", "gp": 65.0, "points": 14.0}]
        )
        assert len(merged) == 2
        assert merged[1]["name"] == "Rookie X"

    def test_overriding_volume_recomputes_the_percentage(self):
        merged = export.apply_overrides(self._rows(), [{"nba_id": "1", "fgm": 4.0, "fga": 16.0}])
        assert merged[0]["fg_pct"] == pytest.approx(0.25)

    def test_no_overrides_leaves_rows_alone(self):
        rows = self._rows()
        assert export.apply_overrides(rows, []) == rows
