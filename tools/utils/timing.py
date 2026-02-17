"""Timing tracker for measuring operation latencies."""

from __future__ import annotations

import time
from typing import Dict, List, Optional, Tuple


class TimingTracker:
    """Track timing for operations with support for nested tracking."""

    def __init__(self):
        """Initialize the timing tracker."""
        self._operations: Dict[str, List[float]] = {}
        self._current_operations: Dict[str, float] = {}
        self._detailed_timings: List[Tuple[str, float, str]] = []

    def start(self, operation: str) -> None:
        """Start timing an operation.

        Args:
            operation: Name of the operation to track
        """
        self._current_operations[operation] = time.perf_counter()

    def end(self, operation: str, detail: Optional[str] = None) -> float:
        """End timing an operation and record the duration.

        Args:
            operation: Name of the operation
            detail: Optional detail string for per-item tracking

        Returns:
            Duration in seconds
        """
        if operation not in self._current_operations:
            return 0.0

        start_time = self._current_operations.pop(operation)
        duration = time.perf_counter() - start_time

        # Record in operations list
        if operation not in self._operations:
            self._operations[operation] = []
        self._operations[operation].append(duration)

        # Record detailed timing if detail provided
        if detail:
            self._detailed_timings.append((operation, duration, detail))

        return duration

    def get_total(self, operation: str) -> float:
        """Get total time for an operation.

        Args:
            operation: Name of the operation

        Returns:
            Total duration in seconds
        """
        return sum(self._operations.get(operation, []))

    def get_count(self, operation: str) -> int:
        """Get count of times an operation was performed.

        Args:
            operation: Name of the operation

        Returns:
            Number of times operation was tracked
        """
        return len(self._operations.get(operation, []))

    def get_average(self, operation: str) -> float:
        """Get average time for an operation.

        Args:
            operation: Name of the operation

        Returns:
            Average duration in seconds
        """
        timings = self._operations.get(operation, [])
        return sum(timings) / len(timings) if timings else 0.0

    def get_detailed_timings(
        self, operation: Optional[str] = None
    ) -> List[Tuple[str, float, str]]:
        """Get detailed timings for specific operation or all operations.

        Args:
            operation: Optional operation name to filter by

        Returns:
            List of (operation, duration, detail) tuples
        """
        if operation:
            return [
                (op, dur, det)
                for op, dur, det in self._detailed_timings
                if op == operation
            ]
        return self._detailed_timings

    def format_duration(self, seconds: float) -> str:
        """Format duration in human-readable format.

        Args:
            seconds: Duration in seconds

        Returns:
            Formatted string (e.g., "1.23s", "45.6ms")
        """
        if seconds >= 1.0:
            return f"{seconds:.2f}s"
        elif seconds >= 0.001:
            return f"{seconds * 1000:.1f}ms"
        else:
            return f"{seconds * 1000000:.0f}µs"

    def get_summary(self) -> Dict[str, Dict[str, float | int | str]]:
        """Get summary of all tracked operations.

        Returns:
            Dictionary with operation stats
        """
        summary = {}
        for operation in self._operations:
            summary[operation] = {
                "total": self.get_total(operation),
                "count": self.get_count(operation),
                "average": self.get_average(operation),
                "formatted_total": self.format_duration(self.get_total(operation)),
                "formatted_average": self.format_duration(self.get_average(operation)),
            }
        return summary

    def format_summary(self) -> str:
        """Format summary as a readable string.

        Returns:
            Multi-line string with timing summary
        """
        summary = self.get_summary()
        if not summary:
            return "No timing data recorded."

        lines = ["[bold cyan]Timing Summary:[/bold cyan]"]

        # Calculate total time across all operations
        total_time = sum(s["total"] for s in summary.values())
        lines.append(f"  Total time: [bold]{self.format_duration(total_time)}[/bold]")
        lines.append("")

        # Show breakdown by operation
        for operation, stats in summary.items():
            percentage = (stats["total"] / total_time * 100) if total_time > 0 else 0

            if stats["count"] > 1:
                lines.append(
                    f"  {operation}: {stats['formatted_total']} "
                    f"({percentage:.1f}%) - {stats['count']} ops, "
                    f"avg {stats['formatted_average']}"
                )
            else:
                lines.append(
                    f"  {operation}: {stats['formatted_total']} ({percentage:.1f}%)"
                )

        return "\n".join(lines)

    def format_detailed(self, operation: str, limit: int = 10) -> str:
        """Format detailed timings for a specific operation.

        Args:
            operation: Operation name to show details for
            limit: Maximum number of details to show (0 for all)

        Returns:
            Multi-line string with detailed timings
        """
        detailed = self.get_detailed_timings(operation)
        if not detailed:
            return f"No detailed timings for {operation}."

        lines = [f"[cyan]Detailed timings for {operation}:[/cyan]"]

        # Sort by duration (slowest first)
        sorted_timings = sorted(detailed, key=lambda x: x[1], reverse=True)

        # Apply limit if specified
        if limit > 0:
            display_timings = sorted_timings[:limit]
            remaining = len(sorted_timings) - limit
        else:
            display_timings = sorted_timings
            remaining = 0

        for _, duration, detail in display_timings:
            lines.append(f"  {detail}: {self.format_duration(duration)}")

        if remaining > 0:
            lines.append(f"  ... and {remaining} more")

        return "\n".join(lines)
