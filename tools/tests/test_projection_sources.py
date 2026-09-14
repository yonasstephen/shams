"""Tests for external projection sources and the ensemble."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.projections import ensemble
from tools.projections.marcel import ProjectedLine
from tools.projections.sources import CsvImportSource, normalize_name
from tools.projections.sources.base import ExternalProjection


def write_csv(path: Path, header: str, *rows: str) -> Path:
    """Write a CSV file for a source to read."""
    path.write_text("\n".join([header, *rows]) + "\n", encoding="utf-8")
    return path


class TestNameNormalization:
    """Sources spell the same player differently."""

    @pytest.mark.parametrize(
        "left,right",
        [
            ("Nikola Jokić", "Nikola Jokic"),
            ("Jaren Jackson Jr.", "Jaren Jackson"),
            ("Royce O'Neale", "Royce ONeale"),
            ("Shai Gilgeous-Alexander", "Shai Gilgeous Alexander"),
            ("  LeBron  James ", "lebron james"),
        ],
    )
    def test_matches(self, left, right):
        assert normalize_name(left) == normalize_name(right)

    def test_distinct_players_stay_distinct(self):
        assert normalize_name("Jalen Williams") != normalize_name("Jaylin Williams")


class TestCsvImport:
    """One parser, many export formats."""

    def test_resolves_aliased_columns(self, tmp_path):
        path = write_csv(
            tmp_path / "a.csv",
            "Player,Tm,GP,MPG,PTS,REB,AST,STL,BLK,TO,3PM,FGM,FGA,FTM,FTA",
            "Nikola Jokic,DEN,70,35,29.5,12.5,10.1,1.3,0.8,3.2,1.1,10.2,17.5,5.5,6.5",
        )
        entries = CsvImportSource(path, name="src").load()
        assert len(entries) == 1
        assert entries[0].per_game["points"] == pytest.approx(29.5)
        assert entries[0].per_game["rebounds"] == pytest.approx(12.5)
        assert entries[0].team == "DEN"

    def test_alternative_headers_also_resolve(self, tmp_path):
        path = write_csv(
            tmp_path / "b.csv",
            "name,games,points,rebounds,assists",
            "LeBron James,70,25.0,7.0,8.0",
        )
        entries = CsvImportSource(path).load()
        assert entries[0].per_game["assists"] == pytest.approx(8.0)

    def test_season_totals_are_detected_and_converted(self, tmp_path):
        """Getting this wrong is a factor-of-seventy error."""
        rows = [f"Player {i},70,{1800 - i * 10},400,300" for i in range(10)]
        path = write_csv(tmp_path / "c.csv", "name,gp,pts,reb,ast", *rows)
        entries = CsvImportSource(path).load()
        assert entries[0].per_game["points"] == pytest.approx(1800 / 70)

    def test_per_game_files_are_left_alone(self, tmp_path):
        rows = [f"Player {i},70,{25 - i},8,5" for i in range(10)]
        path = write_csv(tmp_path / "d.csv", "name,gp,pts,reb,ast", *rows)
        entries = CsvImportSource(path).load()
        assert entries[0].per_game["points"] == pytest.approx(25.0)

    def test_blank_and_placeholder_cells(self, tmp_path):
        path = write_csv(
            tmp_path / "e.csv", "name,gp,pts,reb", "A B,70,-,8", "C D,70,20,"
        )
        entries = CsvImportSource(path).load()
        by_name = {e.name: e for e in entries}
        assert "points" not in by_name["A B"].per_game
        assert by_name["C D"].per_game["points"] == pytest.approx(20.0)

    def test_rows_without_games_are_dropped(self, tmp_path):
        path = write_csv(tmp_path / "f.csv", "name,gp,pts", "A B,0,10", "C D,70,20")
        assert [e.name for e in CsvImportSource(path).load()] == ["C D"]

    def test_missing_file_is_not_fatal(self, tmp_path):
        assert CsvImportSource(tmp_path / "nope.csv").load() == []

    def test_unrecognizable_header_is_not_fatal(self, tmp_path):
        path = write_csv(tmp_path / "g.csv", "alpha,beta", "1,2")
        assert CsvImportSource(path).load() == []


class TestConsensus:
    """Blending sources."""

    class _Stub:
        def __init__(self, name, entries):
            self.name = name
            self._entries = entries

        def load(self):
            return self._entries

    def _entry(self, name, source, points, games=70.0):
        return ExternalProjection(
            name=name, source=source, games=games, per_game={"points": points}
        )

    def test_median_not_mean(self):
        """One wild outlier must not drag the blend."""
        sources = [
            self._Stub("a", [self._entry("A B", "a", 20.0)]),
            self._Stub("b", [self._entry("A B", "b", 22.0)]),
            self._Stub("c", [self._entry("A B", "c", 90.0)]),
        ]
        merged = ensemble.build_consensus(sources)
        assert merged[normalize_name("A B")].per_game["points"] == pytest.approx(22.0)

    def test_joins_across_spellings(self):
        sources = [
            self._Stub("a", [self._entry("Nikola Jokić", "a", 29.0)]),
            self._Stub("b", [self._entry("Nikola Jokic", "b", 30.0)]),
        ]
        merged = ensemble.build_consensus(sources)
        assert len(merged) == 1
        assert merged[normalize_name("Nikola Jokic")].source_count == 2

    def test_a_failing_source_does_not_break_the_blend(self):
        class Broken:
            name = "broken"

            def load(self):
                raise RuntimeError("boom")

        merged = ensemble.build_consensus(
            [Broken(), self._Stub("ok", [self._entry("A B", "ok", 20.0)])]
        )
        assert len(merged) == 1


class TestDisagreementsAndGaps:
    """Benchmarking and the blind spot."""

    def _projection(self, name, points):
        line = ProjectedLine(nba_id=1, name=name, games=70.0, minutes_per_game=30.0)
        line.per_game = {"points": points}
        return line

    def _consensus(self, name, points, sources=("a", "b")):
        return ensemble.Consensus(
            key=normalize_name(name),
            name=name,
            sources=list(sources),
            games=70.0,
            per_game={"points": points},
        )

    def test_large_gaps_are_flagged(self):
        projections = {1: self._projection("A B", 10.0)}
        consensus = {normalize_name("A B"): self._consensus("A B", 20.0)}
        flagged = ensemble.find_disagreements(projections, consensus)
        assert len(flagged) == 1
        assert flagged[0].relative_gap == pytest.approx(0.5)

    def test_agreement_is_not_flagged(self):
        projections = {1: self._projection("A B", 20.0)}
        consensus = {normalize_name("A B"): self._consensus("A B", 21.0)}
        assert not ensemble.find_disagreements(projections, consensus)

    def test_flagged_sorted_by_gap(self):
        projections = {1: self._projection("A B", 10.0), 2: self._projection("C D", 5.0)}
        consensus = {
            normalize_name("A B"): self._consensus("A B", 15.0),
            normalize_name("C D"): self._consensus("C D", 20.0),
        }
        flagged = ensemble.find_disagreements(projections, consensus)
        assert [f.name for f in flagged] == ["C D", "A B"]

    def test_rookies_surface_as_missing(self):
        projections = {1: self._projection("Veteran Guy", 20.0)}
        consensus = {
            normalize_name("Veteran Guy"): self._consensus("Veteran Guy", 20.0),
            normalize_name("Rookie Guy"): self._consensus("Rookie Guy", 14.0),
        }
        missing = ensemble.missing_from_model(projections, consensus)
        assert [m.name for m in missing] == ["Rookie Guy"]

    def test_missing_players_render_as_export_rows(self):
        entry = self._consensus("Rookie Guy", 14.0)
        entry.per_game.update({"fgm": 5.0, "fga": 10.0, "ftm": 2.0, "fta": 4.0})
        rows = ensemble.as_export_rows([entry])
        assert rows[0]["name"] == "Rookie Guy"
        assert rows[0]["fg_pct"] == pytest.approx(0.5)
        assert rows[0]["source"].startswith("consensus:")

    def test_rows_without_games_are_skipped(self):
        entry = self._consensus("Nobody", 5.0)
        entry.games = 0.0
        assert not ensemble.as_export_rows([entry])
