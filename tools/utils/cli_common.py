"""Common interactive CLI utilities for Shams."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, Mapping, Optional, Sequence, Tuple

from prompt_toolkit import prompt as pt_prompt
from prompt_toolkit.completion import FuzzyWordCompleter
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from rich.console import Console
from rich.table import Table

console = Console()


def _stdin_isatty() -> bool:
    """Check if stdin is a TTY (terminal)."""
    return sys.stdin.isatty()


@dataclass
class CommandContext:
    """Holds CLI command metadata."""

    name: str
    handler: Callable[[str], None]
    description: str


class CommandRegistry:
    """Registers and dispatches CLI commands."""

    def __init__(self) -> None:
        self._commands: Dict[str, CommandContext] = {}

    def register(
        self, command: str, handler: Callable[[str], None], description: str
    ) -> None:
        self._commands[command] = CommandContext(command, handler, description)

    def get(self, command: str) -> Optional[CommandContext]:
        return self._commands.get(command)

    def descriptions(self) -> Iterable[CommandContext]:
        return self._commands.values()

    def names(self) -> Sequence[str]:
        return tuple(sorted(self._commands))


def prompt_with_completion(commands: Sequence[str], base_prompt: str = "/") -> str:
    kb = KeyBindings()

    @kb.add("escape")
    def _(event) -> None:  # pragma: no cover - interactive
        event.app.exit(result="")

    # Setup persistent history file
    history_file = Path.home() / ".shams" / "history"
    history_file.parent.mkdir(parents=True, exist_ok=True)

    history = FileHistory(str(history_file))

    if commands and _stdin_isatty():
        completer = FuzzyWordCompleter(commands)
        return pt_prompt(
            f"{base_prompt} ",
            completer=completer,
            complete_in_thread=True,
            complete_while_typing=True,
            key_bindings=kb,
            history=history,
        ).strip()

    if _stdin_isatty():
        return pt_prompt(f"{base_prompt} ", key_bindings=kb, history=history).strip()

    return input(f"{base_prompt} ").strip()


def configure_history() -> None:
    """Enable readline history navigation (up/down)."""

    try:
        import readline

        readline.parse_and_bind("tab: complete")
        readline.parse_and_bind("set enable-keypad on")
        readline.parse_and_bind(r"\e[A: history-search-backward")
        readline.parse_and_bind(r"\e[B: history-search-forward")
    except Exception:  # noqa: BLE001
        return


def show_capabilities(
    registry: CommandRegistry,
    aliases: Optional[Mapping[str, Sequence[str]]] = None,
) -> None:
    table = Table(title="Shams CLI Capabilities")
    table.add_column("Command", justify="left")
    table.add_column("Description", justify="left")

    already_rendered: set[str] = set()
    alias_lookup = aliases or {}

    for ctx in registry.descriptions():
        if ctx.name in already_rendered:
            continue

        alias_list = list(alias_lookup.get(ctx.name, ()))
        label = " , ".join([ctx.name, *alias_list]) if alias_list else ctx.name
        table.add_row(label, ctx.description)

        already_rendered.add(ctx.name)
        already_rendered.update(alias_list)

    console.print(table)

    # Show cache information
    try:
        from tools.boxscore import boxscore_cache

        cache_start, cache_end = boxscore_cache.get_cached_date_range()
        metadata = boxscore_cache.load_metadata()

        if cache_end:
            games_count = metadata.get("games_cached", 0)
            season = metadata.get("season", "")
            console.print()
            console.print(
                f"[dim]Cache: {games_count} games through {cache_end.isoformat()} (Season: {season})[/dim]"
            )
    except Exception:
        # Silently fail if cache info unavailable
        pass


def render_command_help(
    command_name: str,
    description: str,
    arguments: Sequence[Mapping[str, str | bool]],
    console_instance: Console,
) -> None:
    """Render help information for a command.

    Args:
        command_name: The command name (e.g., '/waiver')
        description: Command description
        arguments: List of argument definitions with 'name', 'required', 'description', 'default'
        console_instance: Rich Console instance to print to
    """
    console_instance.print(f"[bold cyan]{command_name}[/bold cyan] - {description}\n")

    if not arguments:
        console_instance.print("This command takes no arguments.\n")
        return

    table = Table(title=f"{command_name} Arguments", show_header=True)
    table.add_column("Argument", justify="left", style="cyan")
    table.add_column("Required", justify="center", style="yellow")
    table.add_column("Default", justify="left", style="green")
    table.add_column("Description", justify="left")

    for arg in arguments:
        name = str(arg.get("name", ""))
        required = "Yes" if arg.get("required") else "No"
        default = str(arg.get("default", "")) if arg.get("default") else "-"
        desc = str(arg.get("description", ""))
        table.add_row(name, required, default, desc)

    console_instance.print(table)


def ask(
    prompt: str = "shams",
    *,
    choices: Optional[Sequence[str]] = None,
    completions: Optional[Sequence[str]] = None,
    show_choices: bool = True,
    strip: bool = True,
) -> str:
    base_prompt = prompt.rstrip(":") + ":"

    if choices and show_choices:
        console.print(f"Options: {', '.join(choices)}", style="cyan")

    while True:
        if choices or not _stdin_isatty():
            response = console.input(f"{base_prompt} ")
        else:
            response = prompt_with_completion(
                completions or (), base_prompt=base_prompt
            )

        if strip:
            response = response.strip()

        if not choices or response in choices:
            if choices:
                try:  # remove non-command entries from history
                    import readline

                    length = readline.get_current_history_length()
                    if length:
                        readline.remove_history_item(length - 1)
                except Exception:  # noqa: BLE001
                    pass
            return response

        console.print(
            f"Invalid choice. Expected one of: {', '.join(choices)}",
            style="yellow",
        )
