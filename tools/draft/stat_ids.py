"""Yahoo stat-id decoding for draft-room stat blobs.

Yahoo's draft store keys every stat blob (``projected_stats``, ``season_stats``,
``average_stats``) by numeric stat id. Two separate concerns live here:

1. **Reading** a blob — needs a static id→name map, because the volume stats
   (FGA/FGM/FTA/FTM) appear in the blobs but are *not* league scoring categories
   and so never show up in ``stat_categories``.
2. **Scoring** — which categories the league actually plays, and which direction
   is better. Both come from the league's own ``stat_categories``, never from a
   hardcoded 9-cat assumption.

Ids verified against live data (see ``docs/draft-room-recon.md``): for LeBron's
projected line, id 4 / id 3 = 463/907 = .510 = id 5, and id 7 / id 6 = 210/278 =
.755 = id 8.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence

# Static map for reading stat blobs. Names match the field names used by
# ``tools.player.player_stats.PlayerStats`` so the existing z-score engine can
# consume these lines without translation.
STAT_ID_TO_NAME: Dict[int, str] = {
    0: "games_played",
    3: "fga",
    4: "fgm",
    5: "fg_pct",
    6: "fta",
    7: "ftm",
    8: "ft_pct",
    10: "threes",
    12: "points",
    15: "rebounds",
    16: "assists",
    17: "steals",
    18: "blocks",
    19: "turnovers",
}

# Percentage categories are ratios, so they are never summed across a roster;
# they are recomputed from the underlying makes and attempts.
RATIO_STATS: Dict[str, tuple] = {
    "fg_pct": ("fgm", "fga"),
    "ft_pct": ("ftm", "fta"),
}

# Stats that describe volume rather than production. Needed to rebuild
# percentages for a whole roster, but not categories in their own right.
VOLUME_STATS = frozenset({"fga", "fgm", "fta", "ftm"})


def parse_stat_blob(blob: Optional[dict]) -> Dict[str, float]:
    """Decode a Yahoo stat blob keyed by stat id into named floats.

    Args:
        blob: Mapping of stat id (as string or int) to a value. Yahoo sends
            strings like ``".510"`` and ``"1221"``; empty and ``"-"`` appear for
            missing data.

    Returns:
        Mapping of canonical stat name to float. Unknown ids are ignored.
    """
    if not blob:
        return {}

    parsed: Dict[str, float] = {}
    for raw_id, raw_value in blob.items():
        try:
            stat_id = int(raw_id)
        except (TypeError, ValueError):
            continue

        name = STAT_ID_TO_NAME.get(stat_id)
        if name is None:
            continue

        parsed[name] = _to_float(raw_value)

    return parsed


def _to_float(value: object) -> float:
    """Coerce a Yahoo stat value to float, treating placeholders as zero."""
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    if not text or text == "-":
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def is_empty_line(stats: Dict[str, float]) -> bool:
    """Whether a decoded stat line carries no information.

    Yahoo projects an all-zero line for inactive and retired players (``inj:
    "NA"``). Those must be treated as *missing*, never as a projection of zero,
    or they drag every league average down and rank as replacement-level rather
    than being excluded.

    Args:
        stats: Decoded stat line.

    Returns:
        True when the line should be treated as absent.
    """
    if not stats:
        return True
    # Games played is the cleanest signal: a real projection always has some.
    if stats.get("games_played", 0) > 0:
        return False
    return not any(value for key, value in stats.items() if key != "games_played")


class StatCategory:
    """One scoring category of the league."""

    __slots__ = ("stat_id", "name", "display_name", "sort_order", "is_display_only")

    def __init__(
        self,
        stat_id: int,
        name: str,
        display_name: str,
        sort_order: int,
        is_display_only: bool,
    ) -> None:
        self.stat_id = stat_id
        self.name = name
        self.display_name = display_name
        self.sort_order = sort_order
        self.is_display_only = is_display_only

    @property
    def higher_is_better(self) -> bool:
        """Whether a larger value wins the category.

        Yahoo encodes this as ``sort_order``: 1 for normal categories, 0 for
        ones where less is better (turnovers). Reading it beats hardcoding a
        turnovers special case, which would be wrong for any league scoring
        something like personal fouls.
        """
        return self.sort_order != 0

    @property
    def is_ratio(self) -> bool:
        """Whether the category is a percentage rebuilt from makes/attempts."""
        return self.name in RATIO_STATS

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<StatCategory {self.display_name} id={self.stat_id}>"


def parse_stat_categories(raw: Optional[Sequence[dict]]) -> List[StatCategory]:
    """Build the league's scoring categories from Yahoo's ``stat_categories``.

    Display-only categories (games played) are dropped, as are any whose stat id
    we cannot decode.

    Args:
        raw: The ``stat_categories`` array from the draft store's settings.

    Returns:
        Scoring categories, in the order Yahoo lists them.
    """
    categories: List[StatCategory] = []
    for entry in raw or []:
        try:
            stat_id = int(entry.get("stat_id"))
        except (TypeError, ValueError):
            continue

        if entry.get("is_only_display_stat"):
            continue

        name = STAT_ID_TO_NAME.get(stat_id)
        if name is None:
            continue

        categories.append(
            StatCategory(
                stat_id=stat_id,
                name=name,
                display_name=str(entry.get("display_name") or name),
                sort_order=int(entry.get("sort_order", 1) or 0),
                is_display_only=False,
            )
        )

    return categories


def required_stat_names(categories: Iterable[StatCategory]) -> List[str]:
    """Every stat name needed to score the given categories.

    Ratio categories pull in their makes and attempts, since a roster's FG% is
    total makes over total attempts rather than an average of percentages.

    Args:
        categories: The league's scoring categories.

    Returns:
        Stat names, de-duplicated, order preserved.
    """
    names: List[str] = []
    for category in categories:
        for name in (category.name, *RATIO_STATS.get(category.name, ())):
            if name not in names:
                names.append(name)
    return names
