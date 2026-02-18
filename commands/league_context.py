"""Shared context for league-related commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Sequence

from rich.console import Console

from tools.utils.cli_common import ask
from tools.utils.render import render_suggestions_table
from tools.utils.yahoo import fetch_user_leagues


class LeagueContext:
    """Manages league selection and defaults for commands."""

    CONFIG_FILE = Path.home() / ".shams" / "config.json"

    def __init__(self, console: Console) -> None:
        self.console = console
        self._default_league_key: Optional[str] = None
        # Ensure ~/.shams/ directory exists
        self.CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        self._load_config()

    def get_default_league_key(self) -> Optional[str]:
        """Get the currently set default league key."""
        return self._default_league_key

    def set_default_league_key(self, league_key: Optional[str]) -> None:
        """Set the default league key and persist to config file."""
        self._default_league_key = league_key
        self._save_config()

    def _load_config(self) -> None:
        """Load configuration from file."""
        if not self.CONFIG_FILE.exists():
            return

        try:
            with open(self.CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
                self._default_league_key = config.get("default_league_key")
        except (json.JSONDecodeError, IOError) as err:
            # If config is corrupted, just start fresh
            self.console.print(
                f"Warning: Could not load config file: {err}", style="yellow"
            )

    def _save_config(self) -> None:
        """Save configuration to file."""
        try:
            config = {"default_league_key": self._default_league_key}
            with open(self.CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
        except IOError as err:
            self.console.print(
                f"Warning: Could not save config file: {err}", style="yellow"
            )

    def select_league(self) -> Optional[str]:
        """Interactively select a league from the user's leagues.

        Note: Does not use status spinner to avoid blocking OAuth prompts.
        """
        # Don't use status spinner here - it blocks OAuth input prompts
        leagues = fetch_user_leagues()

        if not leagues:
            self.console.print(
                "No leagues found for the authenticated user.", style="red"
            )
            return None

        table = render_suggestions_table(
            [
                {"full_name": f"{league.get('name')} ({league.get('league_key')})"}
                for league in leagues
            ]
        )
        table.title = "Select a League"
        self.console.print(table)

        selection = ask(
            "Choose league by number",
            choices=[str(i) for i in range(1, len(leagues) + 1)],
            show_choices=False,
        )
        return leagues[int(selection) - 1].get("league_key")

    def resolve_league_key(self, parts: Sequence[str]) -> Optional[str]:
        """Resolve a league key from command parts or use default."""
        if len(parts) > 1:
            return parts[1]

        league_key = self.get_default_league_key()
        if not league_key:
            self.console.print(
                "No default league set. Use /set-league first.", style="yellow"
            )
        return league_key
