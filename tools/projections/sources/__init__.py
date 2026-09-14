"""External projection sources.

Our model cannot see what has not happened yet: a rookie with no NBA history, a
free agent who changed teams, a guard who just lost his starting job. Those are
exactly the players who decide a draft, and public projections — which are made
by people watching the offseason — do see them.

Sources are adapters behind one interface, so a blend of two is the same code
path as a blend of five, and a source that goes stale can be dropped by deleting
one file.

Every adapter here reads a **file the user already has** — the CSV or JSON export
these services offer. That is a deliberate choice over scraping: an export is a
stable contract, an HTML page is not, and a parser written against markup I
cannot re-verify would break silently in October. Adding a fetching adapter later
only means implementing :class:`~tools.projections.sources.base.Source`.
"""

from tools.projections.sources.base import (
    ExternalProjection,
    Source,
    normalize_name,
)
from tools.projections.sources.csv_import import CsvImportSource

__all__ = ["ExternalProjection", "Source", "CsvImportSource", "normalize_name"]
