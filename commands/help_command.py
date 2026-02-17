"""Help command for the Shams CLI."""

from __future__ import annotations

from typing import Mapping, Optional, Sequence

from rich.console import Console

from commands import Command
from tools.utils.cli_common import CommandRegistry, show_capabilities


class HelpCommand(Command):
    """Display available commands."""

    def __init__(
        self,
        console: Console,
        registry: CommandRegistry,
        aliases: Optional[Mapping[str, Sequence[str]]] = None,
    ) -> None:
        super().__init__(console)
        self.registry = registry
        self._alias_map = aliases

    @property
    def name(self) -> str:
        return "/help"

    @property
    def description(self) -> str:
        return "Display available commands."

    def execute(self, command: str) -> None:
        if self.should_show_help(command):
            self.show_help()
            return
        show_capabilities(self.registry, self._alias_map)
