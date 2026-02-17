"""Pydantic models for API responses."""

from typing import Dict, List, Optional

from pydantic import BaseModel


class PlayerStats(BaseModel):
    """Player statistics for a period."""

    fg_pct: float
    ft_pct: float
    fgm: float
    fga: float
    ftm: float
    fta: float
    threes: float
    points: float
    rebounds: float
    assists: float
    steals: float
    blocks: float
    turnovers: float
    usage_pct: float
    games_count: int
    games_started: int
    minutes: float
    last_game_date: Optional[str] = None


class GameLog(BaseModel):
    """Individual game log entry."""

    date: str
    matchup: str
    fantasy_week: Optional[int] = None
    wl: Optional[str] = None  # "W" or "L" for win/loss
    score: Optional[str] = None  # Score in format "101-98"
    minutes: float
    fg_pct: float
    ft_pct: float
    fgm: float
    fga: float
    ftm: float
    fta: float
    threes: float
    points: float
    rebounds: float
    assists: float
    steals: float
    blocks: float
    turnovers: float
    usage_pct: float = 0.0


class PlayerStatsResponse(BaseModel):
    """Response for player stats endpoint."""

    player_id: int
    player_name: str
    team_tricode: Optional[str] = None
    rank: Optional[int] = None
    last_game: Optional[PlayerStats]
    last3: Optional[PlayerStats]
    last7: Optional[PlayerStats]
    season: Optional[PlayerStats]
    trend: float
    recent_games: List[GameLog] = []
    upcoming_games: List[GameLog] = []
    current_week_remaining_games: int = 0


class PlayerSuggestion(BaseModel):
    """Player search suggestion."""

    player_id: int
    full_name: str
    first_name: str
    last_name: str


class PlayerSearchResponse(BaseModel):
    """Response for player search."""

    suggestions: List[PlayerSuggestion]
    exact_match: bool


class WaiverPlayer(BaseModel):
    """Waiver wire player."""

    name: str
    player_id: Optional[int] = None
    rank: Optional[int] = None
    trend: float
    minutes: float
    status: str
    injury_status: str = ""
    injury_note: str = ""
    stats: Optional[PlayerStats]
    last_game_date: Optional[str] = None
    remaining_games: int = 0
    total_games: int = 0
    next_week_games: int = 0
    has_back_to_back: bool = False


class WaiverResponse(BaseModel):
    """Response for waiver wire endpoint."""

    players: List[WaiverPlayer]
    total_count: int
    stats_mode: str
    agg_mode: str
    current_week: int
    cache_info: Optional[Dict] = None


class MatchupTeam(BaseModel):
    """Team in a matchup."""

    team_name: str
    team_key: str
    team_points: float
    projected_team_points: float
    team_ties: float = 0.0
    projected_team_ties: float = 0.0


class MatchupStat(BaseModel):
    """Matchup category stat."""

    stat_id: str
    stat_name: str
    current: float
    projected: float


class PlayerContribution(BaseModel):
    """Player's contribution to team stats."""

    player_key: str
    player_name: str
    player_id: Optional[int] = None
    total_games: int
    remaining_games: int
    games_played: int = 0
    stats: Dict[str, float]
    shooting: Dict[str, float]
    is_on_roster_today: bool = True


class MatchupProjectionResponse(BaseModel):
    """Response for matchup projection endpoint."""

    week: int
    week_start: str
    week_end: str
    user_team: MatchupTeam
    opponent_team: MatchupTeam
    stat_categories: List[Dict]
    user_current: Dict[str, float]
    user_projection: Dict[str, float]
    opponent_current: Dict[str, float]
    opponent_projection: Dict[str, float]
    current_player_contributions: List[
        PlayerContribution
    ]  # Actual stats accumulated so far this week
    opponent_current_player_contributions: List[PlayerContribution]
    player_contributions: List[PlayerContribution]  # Remaining projected contributions
    opponent_player_contributions: List[PlayerContribution]
    remaining_days_projection: Dict[str, Dict[str, Dict[str, float]]]
    player_positions: Dict[str, Dict[str, str]] = {}
    opponent_remaining_days_projection: Dict[str, Dict[str, Dict[str, float]]] = {}
    opponent_player_positions: Dict[str, Dict[str, str]] = {}
    projection_mode: str = "season"
    optimize_user_roster: bool = False
    optimize_opponent_roster: bool = False


class LeagueMatchup(BaseModel):
    """Single matchup in league."""

    week: int
    week_start: str
    week_end: str
    teams: List[MatchupTeam]
    stat_categories: List[Dict]


class AllMatchupsResponse(BaseModel):
    """Response for all league matchups."""

    league_name: str
    week: int
    matchups: List[LeagueMatchup]
    user_team_key: str


class TeamScheduleDay(BaseModel):
    """Single day in team schedule."""

    date: str
    is_playing: bool
    is_past: bool


class TeamScheduleInfo(BaseModel):
    """Team schedule information."""

    team_id: int
    team_name: str
    team_abbr: str
    current_week_games: int
    current_week_total: int
    next_week_games: int
    current_week_dates: List[TeamScheduleDay]
    next_week_dates: List[TeamScheduleDay]


class TeamScheduleResponse(BaseModel):
    """Response for team schedule endpoint."""

    teams: List[TeamScheduleInfo]
    current_week: int
    next_week: int


class RankedPlayer(BaseModel):
    """Player with ranking and season stats."""

    player_id: int
    player_name: str
    team_tricode: Optional[str] = None
    rank: int
    stats: Optional[PlayerStats] = None
    z_score: Optional[float] = None


class RankedPlayersResponse(BaseModel):
    """Response for ranked players endpoint."""

    players: List[RankedPlayer]
    total_count: int
