"""Command modules for the Shams CLI."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Sequence

from rich.console import Console


class Command(ABC):
    """Base class for CLI commands."""

    def __init__(self, console: Console) -> None:
        self.console = console

    @property
    @abstractmethod
    def name(self) -> str:
        """Primary command name (e.g., '/help')."""

    @property
    def aliases(self) -> Sequence[str]:
        """Additional aliases for this command (e.g., ['/quit'] for '/exit')."""
        return ()

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of what this command does."""

    @property
    def arguments(self) -> List[Dict[str, str | bool]]:
        """Return list of argument definitions for this command.

        Each argument is a dict with keys:
        - name: The argument name (e.g., '-r', '--sort', '<player_name>')
        - required: Boolean indicating if the argument is required
        - description: Human-readable description of the argument
        - default: (optional) Default value if not provided

        Returns empty list by default (no arguments).
        """
        return []

    def should_show_help(self, command: str) -> bool:
        """Check if help flag (-h or --help) is present in command string."""
        parts = command.split()
        return "-h" in parts or "--help" in parts

    def show_help(self) -> None:
        """Display help information for this command."""
        from tools.utils.cli_common import render_command_help

        render_command_help(self.name, self.description, self.arguments, self.console)

    @abstractmethod
    def execute(self, command: str) -> None:
        """Execute the command with the full command string."""


class CommandError(Exception):
    """Custom exception for command parsing errors."""
