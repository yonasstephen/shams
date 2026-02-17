"""Retry decorator with exponential backoff for API calls."""

from __future__ import annotations

import time
from functools import wraps
from typing import Any, Callable, Optional, Tuple, Type

from rich.console import Console

_console = Console()

# Global progress display for persisting error messages
_progress_display = None


def set_progress_display(display) -> None:
    """Set the progress display for error/retry messages."""
    global _progress_display
    _progress_display = display


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 10.0,
    exponential_base: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    silent: bool = False,
) -> Callable:
    """Decorator to retry a function with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts (default: 3)
        base_delay: Initial delay in seconds (default: 1.0)
        max_delay: Maximum delay in seconds (default: 10.0)
        exponential_base: Base for exponential backoff (default: 2.0)
        exceptions: Tuple of exception types to catch (default: all exceptions)
        silent: If True, don't print retry messages (default: False)

    Returns:
        Decorated function with retry logic

    Example:
        @retry_with_backoff(max_retries=3, base_delay=2.0)
        def fetch_data():
            return api.get("/data")
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception: Optional[Exception] = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt == max_retries:
                        # Final attempt failed - persist error message only if not silent
                        if not silent:
                            error_msg = f"[red]✗[/red] {func.__name__} failed after {max_retries + 1} attempts: {e}"
                            if _progress_display:
                                _progress_display.add_line(error_msg)
                            else:
                                _console.print(error_msg)
                        raise

                    # Calculate delay with exponential backoff
                    delay = min(base_delay * (exponential_base**attempt), max_delay)

                    # Persist retry warning
                    if not silent:
                        warning_msg = (
                            f"[yellow]⚠[/yellow] {func.__name__} failed (attempt {attempt + 1}/{max_retries + 1}), "
                            f"retrying in {delay:.1f}s... ({type(e).__name__})"
                        )
                        if _progress_display:
                            _progress_display.add_line(warning_msg)
                        else:
                            _console.print(warning_msg)

                    time.sleep(delay)

            # Should never reach here, but just in case
            if last_exception:
                raise last_exception
            return None

        return wrapper

    return decorator
