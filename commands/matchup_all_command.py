"""League-wide matchup projection command for the Shams CLI."""

from __future__ import annotations

from typing import Dict, List

from rich.console import Console

from commands import Command
from commands.league_context import LeagueContext
from commands.matchup_command import render_league_matchups
from tools.matchup.matchup_projection import project_league_matchups


class MatchupAllCommand(Command):
    """Display projections for every matchup in the league."""

    def __init__(self, console: Console, league_context: LeagueContext) -> None:
        super().__init__(console)
        self.league_context = league_context

    @property
    def name(self) -> str:
        return "/matchup-all"

    @property
    def description(self) -> str:
        return "Display projections for every matchup in the league."

    @property
    def arguments(self) -> List[Dict[str, str | bool]]:
        return [
            {
                "name": "[league_key]",
                "required": False,
                "default": "default league",
                "description": "Yahoo league key",
            },
        ]

    def execute(self, command: str) -> None:
        if self.should_show_help(command):
            self.show_help()
            return
        parts = command.split()
        league_key = self.league_context.resolve_league_key(parts)
        if not league_key:
            return

        with self.console.status(
            "[cyan]Computing all matchup projections...", spinner="dots"
        ):
            try:
                projections = project_league_matchups(league_key)
            except Exception as err:  # noqa: BLE001
                self.console.print(
                    f"Error projecting league matchups: {err}", style="red"
                )
                return

        matchups = projections.get("matchups", [])
        if not matchups:
            self.console.print(
                "No matchups available for the current week.", style="yellow"
            )
            return

        week = projections.get("week")
        self.console.print(
            f"[bold green]League matchup projections (Week {week})[/bold green]"
        )

        for table in render_league_matchups(
            league_name=league_key,
            week=week,
            matchups=matchups,
        ):
            self.console.print(table)
