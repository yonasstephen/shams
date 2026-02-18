"""Configuration for stat color thresholds."""

from __future__ import annotations

import os


def _resolve_float_env(env_var: str, default: float) -> float:
    """Resolve a float value from an environment variable.

    Args:
        env_var: Environment variable name
        default: Default value if not set or invalid

    Returns:
        Float value from environment or default
    """
    value = os.environ.get(env_var)
    if value is None:
        return default
    try:
        # Strip comments (text after #) and whitespace
        return float(value.split("#", 1)[0].strip())
    except (TypeError, ValueError):
        return default


class StatThresholds:
    """Container for stat color thresholds loaded from environment."""

    def __init__(self):
        """Load all thresholds from environment variables."""
        # Points (PTS)
        self.pts_yellow_min = _resolve_float_env("STAT_PTS_YELLOW_MIN", 5.0)
        self.pts_green_min = _resolve_float_env("STAT_PTS_GREEN_MIN", 13.0)

        # Rebounds (REB)
        self.reb_yellow_min = _resolve_float_env("STAT_REB_YELLOW_MIN", 5.0)
        self.reb_green_min = _resolve_float_env("STAT_REB_GREEN_MIN", 9.0)

        # Assists (AST)
        self.ast_yellow_min = _resolve_float_env("STAT_AST_YELLOW_MIN", 3.0)
        self.ast_green_min = _resolve_float_env("STAT_AST_GREEN_MIN", 6.0)

        # Three-Pointers Made (3PM)
        self.threes_yellow_min = _resolve_float_env("STAT_3PM_YELLOW_MIN", 2.0)
        self.threes_green_min = _resolve_float_env("STAT_3PM_GREEN_MIN", 4.0)

        # Steals (STL)
        self.stl_yellow_min = _resolve_float_env("STAT_STL_YELLOW_MIN", 2.0)
        self.stl_green_min = _resolve_float_env("STAT_STL_GREEN_MIN", 3.0)

        # Blocks (BLK)
        self.blk_yellow_min = _resolve_float_env("STAT_BLK_YELLOW_MIN", 2.0)
        self.blk_green_min = _resolve_float_env("STAT_BLK_GREEN_MIN", 3.0)

        # Turnovers (TO) - INVERSE: lower is better
        self.to_green_max = _resolve_float_env("STAT_TO_GREEN_MAX", 2.0)
        self.to_yellow_max = _resolve_float_env("STAT_TO_YELLOW_MAX", 4.0)

        # Field Goal Percentage (FG%)
        self.fg_pct_red_max = _resolve_float_env("STAT_FG_PCT_RED_MAX", 0.30)
        self.fg_pct_yellow_max = _resolve_float_env("STAT_FG_PCT_YELLOW_MAX", 0.50)

        # Free Throw Percentage (FT%)
        self.ft_pct_red_max = _resolve_float_env("STAT_FT_PCT_RED_MAX", 0.60)
        self.ft_pct_yellow_max = _resolve_float_env("STAT_FT_PCT_YELLOW_MAX", 0.80)

        # Usage Percentage (USG%)
        self.usg_pct_yellow_min = _resolve_float_env("STAT_USG_PCT_YELLOW_MIN", 0.15)
        self.usg_pct_green_min = _resolve_float_env("STAT_USG_PCT_GREEN_MIN", 0.25)

        # Minutes (MIN)
        self.min_yellow_min = _resolve_float_env("STAT_MIN_YELLOW_MIN", 10.0)
        self.min_green_min = _resolve_float_env("STAT_MIN_GREEN_MIN", 18.0)


# Singleton instance - load once on import
_thresholds = StatThresholds()


def get_thresholds() -> StatThresholds:
    """Get the global stat thresholds instance.

    Returns:
        StatThresholds instance with all configured thresholds
    """
    return _thresholds
