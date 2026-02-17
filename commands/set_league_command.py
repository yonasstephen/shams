"""Set league command for the Shams CLI."""

from __future__ import annotations

from typing import Dict, List

from rich.console import Console

from commands import Command
from commands.league_context import LeagueContext


class SetLeagueCommand(Command):
    """Set or update the default Yahoo league."""

    def __init__(self, console: Console, league_context: LeagueContext) -> None:
        super().__init__(console)
        self.league_context = league_context

    @property
    def name(self) -> str:
        return "/set-league"

    @property
    def description(self) -> str:
        return "Set or update the default Yahoo league used by other commands."

    @property
    def arguments(self) -> List[Dict[str, str | bool]]:
        return [
            {
                "name": "[league_key]",
                "required": False,
                "default": "interactive selection",
                "description": "Yahoo league key",
            },
        ]

    def execute(self, command: str) -> None:
        if self.should_show_help(command):
            self.show_help()
            return
        parts = command.split()
        explicit = parts[1] if len(parts) > 1 else None
        league_key = explicit or self.league_context.get_default_league_key()

        if not league_key:
            self.console.print("No default league set; fetching leagues...")
            league_key = self.league_context.select_league()
            if not league_key:
                self.console.print(
                    "No league selected; default unchanged.", style="yellow"
                )
                return

        self.league_context.set_default_league_key(league_key)
        self.console.print(f"Default league set to {league_key}.", style="green")
