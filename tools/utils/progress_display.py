"""Progressive live display for long-running operations."""

from __future__ import annotations

from typing import List

from rich.console import Console, Group
from rich.live import Live
from rich.spinner import Spinner
from rich.text import Text


class ProgressDisplay:
    """Manages progressive display where completed steps persist."""

    def __init__(self, console: Console):
        """Initialize progress display.

        Args:
            console: Rich console instance
        """
        self.console = console
        self.completed_lines: List[str] = []
        self.current_status: str | None = None
        self.live: Live | None = None

    def start(self) -> None:
        """Start the live display."""
        self.live = Live(
            self._render(), console=self.console, refresh_per_second=10, transient=False
        )
        self.live.start()

    def stop(self) -> None:
        """Stop the live display."""
        if self.live:
            self.live.stop()
            self.live = None

    def update_status(self, message: str) -> None:
        """Update the current operation status (shown with spinner).

        Args:
            message: Status message to display
        """
        self.current_status = message
        if self.live:
            self.live.update(self._render())

    def complete_step(self, message: str) -> None:
        """Mark current step as complete and add to completed lines.

        Args:
            message: Completion message (should include ✓)
        """
        self.completed_lines.append(message)
        self.current_status = None
        if self.live:
            self.live.update(self._render())

    def add_line(self, message: str) -> None:
        """Add a line directly to completed (for errors or info).

        Args:
            message: Message to add
        """
        self.completed_lines.append(message)
        if self.live:
            self.live.update(self._render())

    def _render(self):
        """Render the current display state."""
        elements = []

        # Add all completed lines
        for line in self.completed_lines:
            elements.append(Text.from_markup(line))

        # Add current status with spinner if present
        if self.current_status:
            spinner = Spinner("dots", text=Text.from_markup(self.current_status))
            elements.append(spinner)

        return Group(*elements) if elements else Text("")

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()
        return False
