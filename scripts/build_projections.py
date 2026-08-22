#!/usr/bin/env python
"""Generate the season's projection CSV.

Ties the offline pipeline together: cached box scores -> Marcel baseline ->
learned residual correction -> CSV, with hand overrides applied on load.

The residual model is fitted on a season that is *not* being projected, so the
correction it applies has been validated out of sample. See
``tools.projections.backtest`` for the numbers that justify it.

Usage:
    pipenv run python scripts/build_projections.py --season 2026-27
    pipenv run python scripts/build_projections.py --season 2026-27 --no-residual
    pipenv run python scripts/build_projections.py --season 2026-27 --template
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.console import Console

from tools.projections import ensemble, export, history, marcel, residual
from tools.projections.sources import CsvImportSource
from tools.projections.experience import experience_map
from tools.utils.season import get_current_season

_console = Console()

#: How many seasons of history the baseline draws on.
_PRIOR_SEASONS = 3


def _season_start_year(season: str) -> int:
    return int(season.split("-")[0])


def _format_season(start_year: int) -> str:
    return f"{start_year}-{str(start_year + 1)[-2:]}"


def prior_seasons(target: str, count: int = _PRIOR_SEASONS) -> List[str]:
    """Seasons before ``target``, most recent first."""
    start = _season_start_year(target)
    return [_format_season(start - offset) for offset in range(1, count + 1)]


def build(
    season: str,
    use_residual: bool = True,
    priors: Optional[Sequence[str]] = None,
    source_files: Optional[Sequence[str]] = None,
) -> int:
    """Build and write the projection CSV for ``season``.

    Returns:
        Number of players written.
    """
    priors = list(priors or prior_seasons(season))
    _console.print(f"[bold]Projecting {season}[/bold] from {', '.join(priors)}")

    loaded = history.load_seasons(priors)
    available = [s for s in priors if loaded.get(s)]
    if not available:
        _console.print(
            "[red]No cached box scores for any prior season.[/red] "
            "Run scripts/backfill_seasons.py first."
        )
        return 0
    for name in available:
        _console.print(f"  {name}: {len(loaded[name])} players")

    experience = experience_map(season)
    projections = marcel.project_season(
        {s: loaded[s] for s in available}, available, experience=experience
    )
    _console.print(f"[green]✓[/green] baseline: {len(projections)} players")

    if use_residual:
        applied = _apply_residual(projections, loaded, available, experience)
        _console.print(f"[green]✓[/green] residual correction applied to {applied}")

    teams, positions = _context(loaded, available)
    rows = export.build_rows(
        projections,
        yahoo_ids=_yahoo_ids(list(projections)),
        teams=teams,
        positions=positions,
    )
    if use_residual:
        for row in rows:
            row.source = "marcel+residual"
    if source_files:
        rows = _blend_external(rows, projections, source_files)

    path = export.csv_path(season)
    written = export.write_csv(rows, path)
    _console.print(f"[green]✓[/green] wrote {written} players to {path}")

    overrides = export.overrides_path(season)
    if overrides.exists():
        _console.print(f"[cyan]note[/cyan] overrides at {overrides} apply on load")
    return written


def _apply_residual(
    projections: Dict[int, marcel.ProjectedLine],
    loaded: Dict[str, Dict[int, history.SeasonLine]],
    available: Sequence[str],
    experience: Dict[int, int],
) -> int:
    """Fit the residual model on an earlier season and apply it.

    The model is trained on ``available[0]`` predicted from ``available[1:]`` —
    a season entirely outside the one being projected.
    """
    if len(available) < 2:
        _console.print("[yellow]⚠[/yellow] not enough history for a residual model")
        return 0

    train_season, train_priors = available[0], list(available[1:])
    train_projections = marcel.project_season(
        {s: loaded[s] for s in train_priors}, train_priors, experience=experience
    )
    actuals = loaded[train_season]

    training = []
    for player_id, projected in train_projections.items():
        actual = actuals.get(player_id)
        if actual is None or actual.minutes < 500:
            continue
        player_history = [
            loaded[s][player_id] for s in train_priors if player_id in loaded[s]
        ]
        if not player_history:
            continue
        training.append(
            (
                residual.build_features(
                    player_history, projected, experience.get(player_id)
                ),
                {
                    stat: actual.per_game(stat) - projected.per_game.get(stat, 0.0)
                    for stat in residual.CORRECTED_STATS
                },
            )
        )

    if not training:
        _console.print("[yellow]⚠[/yellow] no residual training data")
        return 0

    models = residual.train(training)
    _console.print(f"  residual fitted on {len(training)} players from {train_season}")

    applied = 0
    for player_id, projected in projections.items():
        player_history = [
            loaded[s][player_id] for s in available if player_id in loaded[s]
        ]
        if not player_history:
            continue
        features = residual.build_features(
            player_history, projected, experience.get(player_id)
        )
        residual.apply_correction(projected, features, models)
        applied += 1
    return applied


def _blend_external(
    rows: List[export.ExportRow],
    projections: Dict[int, marcel.ProjectedLine],
    source_files: Sequence[str],
) -> List[export.ExportRow]:
    """Add consensus players our model cannot see, and report disagreements.

    Only players the model is *missing* are taken from the consensus. Where both
    have an opinion, ours stands — the backtest is the evidence for it, and
    silently averaging away a validated model would throw that away. The
    disagreements are printed instead, as a shortlist worth eyeballing.
    """
    sources = [CsvImportSource(Path(path)) for path in source_files]
    consensus = ensemble.build_consensus(sources)
    if not consensus:
        _console.print("[yellow]⚠[/yellow] no usable external projections")
        return rows
    _console.print(f"[green]✓[/green] consensus over {len(consensus)} players")

    missing = ensemble.missing_from_model(projections, consensus)
    for row in ensemble.as_export_rows(missing):
        rows.append(
            export.ExportRow(
                nba_id=0,
                name=str(row["name"]),
                per_game={stat: float(row[stat]) for stat in export.STAT_COLUMNS},
                games=float(row["gp"]),
                minutes_per_game=float(row["mpg"]),
                team=str(row["team"]),
                positions=str(row["positions"]),
                source=str(row["source"]),
                confidence=float(row["confidence"]),
            )
        )
    _console.print(
        f"[green]✓[/green] added {len(missing)} players the model could not see "
        "(rookies, role changes)"
    )

    flagged = ensemble.find_disagreements(projections, consensus)
    if flagged:
        _console.print(
            f"[yellow]{len(flagged)}[/yellow] players disagree with consensus by "
            f">{int(ensemble.DISAGREEMENT_THRESHOLD * 100)}% on points — review these:"
        )
        for item in flagged[:10]:
            _console.print(
                f"    {item.name:26s} ours {item.ours:5.1f}  "
                f"consensus {item.consensus:5.1f}  ({item.sources} sources)"
            )
    return rows


def _team_abbreviations() -> Dict[int, str]:
    """NBA team id -> abbreviation, inverting the static team table."""
    try:
        from nba_api.stats.static import teams as static_teams

        return {
            team["id"]: team.get("abbreviation", "")
            for team in static_teams.get_teams()
        }
    except Exception:  # pylint: disable=broad-except
        return {}


def _yahoo_ids(nba_ids: Sequence[int]) -> Dict[int, str]:
    """NBA id -> Yahoo id, for the players the index already knows.

    Only players seen through a Yahoo league appear, so this is usually partial.
    CsvSource falls back to name matching for the rest, which is why the export
    is still useful with an empty column.
    """
    try:
        from tools.utils import player_index
    except ImportError:
        return {}

    mapping: Dict[int, str] = {}
    for nba_id in nba_ids:
        try:
            yahoo_id = player_index.get_yahoo_id_for_nba_id(nba_id)
        except Exception:  # pylint: disable=broad-except
            continue
        if yahoo_id:
            mapping[nba_id] = str(yahoo_id)
    return mapping


def _context(
    loaded: Dict[str, Dict[int, history.SeasonLine]], available: Sequence[str]
) -> tuple:
    """Most recent team abbreviation and a position placeholder per player.

    Box scores carry team but not fantasy eligibility; positions come from the
    draft room at draft time, so the column exists for the overrides file to
    fill rather than being invented here.
    """
    abbreviations = _team_abbreviations()
    teams: Dict[int, str] = {}
    positions: Dict[int, str] = {}
    # Oldest first, so the most recent season wins on a trade.
    for season in reversed(list(available)):
        for player_id, line in loaded[season].items():
            team_id = line.primary_team_id
            if team_id is not None:
                teams[player_id] = abbreviations.get(team_id, str(team_id))
    return teams, positions


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point."""
    parser = argparse.ArgumentParser(description="Build the projection CSV.")
    parser.add_argument("--season", default=None, help="Season to project, e.g. 2026-27")
    parser.add_argument(
        "--priors", nargs="+", help="Override the prior seasons, most recent first"
    )
    parser.add_argument(
        "--no-residual", action="store_true", help="Baseline only, no correction"
    )
    parser.add_argument(
        "--sources",
        nargs="+",
        help="External projection CSV exports to blend for rookies and role changes",
    )
    parser.add_argument(
        "--template",
        action="store_true",
        help="Also write an empty overrides file listing every player",
    )
    args = parser.parse_args(argv)

    season = args.season or get_current_season()
    written = build(
        season,
        use_residual=not args.no_residual,
        priors=args.priors,
        source_files=args.sources,
    )
    if not written:
        return 1

    if args.template:
        names = [str(row.get("name", "")) for row in export.read_csv(export.csv_path(season))]
        path = export.write_override_template(season, names)
        _console.print(f"[green]✓[/green] overrides template at {path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
