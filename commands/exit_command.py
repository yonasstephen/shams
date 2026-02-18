"""Exit command for the Shams CLI."""

from __future__ import annotations

from typing import Sequence

from commands import Command


class ExitCommand(Command):
    """Exit the CLI application."""

    @property
    def name(self) -> str:
        return "/exit"

    @property
    def aliases(self) -> Sequence[str]:
        return ("/quit",)

    @property
    def description(self) -> str:
        return "Exit the CLI."

    def execute(self, command: str) -> None:
        if self.should_show_help(command):
            self.show_help()
