"""Pydantic models for the live draft assistant."""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class DraftStateRequest(BaseModel):
    """Raw draft-room state POSTed by the Chrome extension.

    Deliberately untyped beyond ``dict``: the extension forwards Yahoo's Redux
    slices with minimal trimming, and ``tools.draft.draft_state`` does the
    interpretation where it can be unit-tested. Pinning a schema here would mean
    a Yahoo shape change breaks with a 422 instead of degrading gracefully.
    """

    draft: Optional[dict] = None
    context: Optional[dict] = None
    countdown: Optional[dict] = None
    draftOrder: Optional[dict] = None  # noqa: N815 - mirrors Yahoo's key
    picks: Optional[List[dict]] = None
    queue: Optional[List] = None
    teams: Optional[dict] = None
    players: Optional[List[dict]] = None
    settings: Optional[dict] = None
    myTeamId: Optional[str] = None  # noqa: N815 - mirrors Yahoo's key
    #: Player ids the user marked drafted by hand, when the adapter missed them.
    manualPicks: Optional[List[str]] = None  # noqa: N815 - matches the wire key


class RosterEntry(BaseModel):
    """A player already on your roster.

    Carries the name because drafted players are absent from the board, so the
    panel has nowhere else to resolve an id from.
    """

    player_id: str
    name: str
    positions: List[str] = Field(default_factory=list)
    nba_team: str = ""
    injury: str = ""


class RecommendationModel(BaseModel):
    """A single player row on the board."""

    player_id: str
    name: str
    positions: List[str] = Field(default_factory=list)
    nba_team: str = ""
    injury: str = ""

    total_value: float
    marginal_value: float
    score: float
    category_z: Dict[str, float] = Field(default_factory=dict)

    standings_delta: Optional[float] = None
    survival: Optional[float] = None
    average_pick: Optional[float] = None
    value_gap: Optional[float] = None
    gap_label: str = ""
    reason: str = ""


class CategorySupplyModel(BaseModel):
    """Supply, demand and runway for one category."""

    name: str
    display_name: str

    my_total: float
    my_rank: int
    league_mean: float
    deficit: float
    is_weakness: bool

    elite_remaining: int
    starter_remaining: int
    best_available: float

    teams_below_mean: int
    crunch: float
    is_supply_crunch: bool

    elite_surviving: float
    cliff_in_picks: Optional[int] = None
    cliff_drop: float = 0.0
    summary: str = ""


class PuntVerdictModel(BaseModel):
    """A simulated punt build."""

    categories: List[str] = Field(default_factory=list)
    label: str
    category_wins: float
    baseline_wins: float
    gain: float
    is_recommended: bool


class DraftBoardResponse(BaseModel):
    """Everything the side panel renders."""

    headline: Optional[RecommendationModel] = None
    alternatives: List[RecommendationModel] = Field(default_factory=list)
    board: List[RecommendationModel] = Field(default_factory=list)

    supply: List[CategorySupplyModel] = Field(default_factory=list)
    heat_map: Dict[str, float] = Field(default_factory=dict)

    punt: Optional[PuntVerdictModel] = None
    punt_options: List[PuntVerdictModel] = Field(default_factory=list)

    my_roster: List[RosterEntry] = Field(default_factory=list)
    positional_gaps: Dict[str, int] = Field(default_factory=dict)
    schedule_available: bool = False
    projection_source: str = ""
    projected_players: int = 0
    picks_until_my_turn: Optional[int] = None
    is_my_turn: bool = False
    seconds_remaining: Optional[int] = None
    current_pick: int = 0
    projected_category_wins: float = 0.0

    # Context echoed back so the panel can label itself without re-parsing.
    league_name: str = ""
    is_mock: bool = False
    num_teams: int = 0
    total_rounds: int = 0
    players_seen: int = 0
    picks_seen: int = 0
    compute_ms: float = 0.0
    warnings: List[str] = Field(default_factory=list)
