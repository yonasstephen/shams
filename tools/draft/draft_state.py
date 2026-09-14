"""Normalized draft state, built from the Yahoo draft-room store payload.

The Chrome extension stays deliberately dumb: it locates the Redux store, trims
the slices we care about, and POSTs them as-is. All interpretation happens here,
where it can be unit-tested against a fixture instead of a live draft.

The payload is treated as untrusted input — every field is optional, because the
one thing guaranteed about a scraped shape is that it will change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from tools.draft import stat_ids
from tools.draft.stat_ids import StatCategory

# Positions that hold a player without them contributing to a weekly lineup.
NON_ACTIVE_POSITIONS = frozenset({"BN", "IL", "IL+"})


@dataclass
class DraftPlayer:
    """One player in the draftable pool."""

    player_id: str
    first_name: str
    last_name: str
    positions: List[str] = field(default_factory=list)
    primary_position: str = ""
    display_position: str = ""
    nba_team: str = ""
    injury: str = ""
    injury_note: str = ""

    # Yahoo's own rankings and market data.
    overall_rank: Optional[int] = None
    projected_rank: Optional[int] = None
    auction_value: Optional[float] = None
    average_pick: Optional[float] = None
    preseason_average_pick: Optional[float] = None
    percent_drafted: Optional[float] = None

    # Stat lines, decoded to canonical names. Season totals, not per-game.
    projected: Dict[str, float] = field(default_factory=dict)
    season: Dict[str, float] = field(default_factory=dict)
    average: Dict[str, float] = field(default_factory=dict)

    @property
    def name(self) -> str:
        """Full display name."""
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def has_projection(self) -> bool:
        """Whether Yahoo supplied a usable projected line.

        Retired and inactive players carry an all-zero line, which must not be
        mistaken for a projection of zero.
        """
        return not stat_ids.is_empty_line(self.projected)

    @property
    def projected_games(self) -> float:
        """Projected games played, falling back to a full-ish season."""
        return self.projected.get("games_played", 0.0)

    def projected_per_game(self) -> Dict[str, float]:
        """Projected season totals converted to per-game rates.

        Percentages are already rates and are passed through untouched;
        everything else is divided by projected games played.
        """
        games = self.projected_games
        if games <= 0:
            return {}

        per_game: Dict[str, float] = {}
        for name, value in self.projected.items():
            if name == "games_played":
                continue
            if name in stat_ids.RATIO_STATS:
                per_game[name] = value
            else:
                per_game[name] = value / games
        return per_game

    def is_injured(self) -> bool:
        """Whether Yahoo flags the player as anything other than healthy."""
        return bool(self.injury)


@dataclass
class DraftPick:
    """A completed pick."""

    pick_number: int
    player_id: str
    team_id: str
    cost: float = 0.0


@dataclass
class DraftTeam:
    """A team in the draft."""

    team_id: str
    name: str
    is_me: bool = False


@dataclass
class RosterSlot:
    """One roster position and how many of it each team must fill."""

    position: str
    count: int

    @property
    def is_active(self) -> bool:
        """Whether players here contribute to weekly scoring."""
        return self.position not in NON_ACTIVE_POSITIONS


@dataclass
class DraftState:
    """The whole draft, normalized."""

    league_id: str = ""
    league_name: str = ""
    season: str = ""
    is_mock: bool = False
    is_auction: bool = False
    num_teams: int = 0
    pick_seconds: int = 0
    seconds_remaining: Optional[int] = None
    draft_status: str = ""

    my_team_id: str = ""
    current_pick: int = 0
    current_team_id: str = ""

    teams: Dict[str, DraftTeam] = field(default_factory=dict)
    players: Dict[str, DraftPlayer] = field(default_factory=dict)
    picks: List[DraftPick] = field(default_factory=list)
    # Overall pick index -> team that owns it. Yahoo publishes the whole order
    # up front, which makes "will he last until my next pick?" exact.
    pick_order: List[str] = field(default_factory=list)
    roster_slots: List[RosterSlot] = field(default_factory=list)
    categories: List[StatCategory] = field(default_factory=list)
    queue: List[str] = field(default_factory=list)

    # ---- derived -------------------------------------------------------

    @property
    def drafted_player_ids(self) -> set:
        """Every player already taken."""
        return {pick.player_id for pick in self.picks}

    def available_players(self, require_projection: bool = True) -> List[DraftPlayer]:
        """Players still on the board.

        Args:
            require_projection: Drop players with no usable projected line.
                These are retired or inactive and are never real picks.

        Returns:
            Available players, ordered by Yahoo's projected rank where known.
        """
        drafted = self.drafted_player_ids
        pool = [
            player
            for pid, player in self.players.items()
            if pid not in drafted and (player.has_projection or not require_projection)
        ]
        pool.sort(key=lambda p: (p.projected_rank is None, p.projected_rank or 0))
        return pool

    def roster(self, team_id: str) -> List[DraftPlayer]:
        """The players a team has drafted, in pick order."""
        return [
            self.players[pick.player_id]
            for pick in self.picks
            if pick.team_id == team_id and pick.player_id in self.players
        ]

    def my_roster(self) -> List[DraftPlayer]:
        """The players you have drafted."""
        return self.roster(self.my_team_id)

    def upcoming_picks_for(self, team_id: str) -> List[int]:
        """Overall pick numbers this team still owns, soonest first."""
        return [
            index
            for index in range(self.current_pick, len(self.pick_order))
            if self.pick_order[index] == team_id
        ]

    def my_upcoming_picks(self) -> List[int]:
        """Overall pick numbers you still own, soonest first."""
        return self.upcoming_picks_for(self.my_team_id)

    def picks_until_my_turn(self) -> Optional[int]:
        """How many picks happen before your next one; 0 if you're on the clock."""
        upcoming = self.my_upcoming_picks()
        if not upcoming:
            return None
        return upcoming[0] - self.current_pick

    def is_my_turn(self) -> bool:
        """Whether you are on the clock."""
        return self.current_team_id == self.my_team_id

    @property
    def total_rounds(self) -> int:
        """Number of rounds, derived from the published pick order."""
        if not self.num_teams:
            return 0
        return len(self.pick_order) // self.num_teams

    @property
    def active_slot_count(self) -> int:
        """Weekly starting-lineup size."""
        return sum(slot.count for slot in self.roster_slots if slot.is_active)

    @property
    def roster_size(self) -> int:
        """Total roster spots per team, bench included."""
        return sum(slot.count for slot in self.roster_slots)


# ---- parsing -----------------------------------------------------------


def _as_int(value: object) -> Optional[int]:
    """Best-effort int coercion; None when the value is absent or junk."""
    if value is None or value == "" or value == "-":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _as_float(value: object) -> Optional[float]:
    """Best-effort float coercion; None when the value is absent or junk."""
    if value is None or value == "" or value == "-":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_player(raw: dict) -> Optional[DraftPlayer]:
    """Build a :class:`DraftPlayer` from one raw store player object."""
    player_id = raw.get("id")
    if player_id is None:
        return None

    return DraftPlayer(
        player_id=str(player_id),
        first_name=str(raw.get("fname") or ""),
        last_name=str(raw.get("lname") or ""),
        positions=[str(p) for p in (raw.get("pos") or [])],
        primary_position=str(raw.get("primary_pos") or ""),
        display_position=str(raw.get("display_pos") or ""),
        nba_team=str(raw.get("team_abbr") or ""),
        injury=str(raw.get("inj") or ""),
        injury_note=str(raw.get("inj_note") or ""),
        overall_rank=_as_int(raw.get("o_rank")),
        projected_rank=_as_int(raw.get("psr_rank")),
        auction_value=_as_float(raw.get("auction-value")),
        average_pick=_as_float(raw.get("average-pick")),
        preseason_average_pick=_as_float(raw.get("preseason-average-pick")),
        percent_drafted=_as_float(raw.get("percent-drafted")),
        projected=stat_ids.parse_stat_blob(raw.get("projected_stats")),
        season=stat_ids.parse_stat_blob(raw.get("season_stats")),
        average=stat_ids.parse_stat_blob(raw.get("average_stats")),
    )


def _parse_roster_slots(raw: Optional[Sequence[dict]]) -> List[RosterSlot]:
    """Build roster slots from the settings' ``roster_positions``."""
    slots: List[RosterSlot] = []
    for entry in raw or []:
        position = entry.get("position")
        if not position:
            continue
        slots.append(RosterSlot(position=str(position), count=int(entry.get("count", 1) or 1)))
    return slots


def _parse_pick_order(raw: Optional[Sequence[dict]]) -> List[str]:
    """Flatten ``draftOrder.order`` into a list of team ids by pick index."""
    order: List[str] = []
    for entry in raw or []:
        team_id = entry.get("teamId")
        order.append(str(team_id) if team_id is not None else "")
    return order


def parse_draft_state(payload: dict) -> DraftState:
    """Build a :class:`DraftState` from the extension's POST body.

    Every field is optional and defaulted. A malformed payload yields a state
    that is empty rather than one that raises — a draft is a bad place to throw.

    Args:
        payload: Trimmed Yahoo draft-store slices, as sent by the extension.

    Returns:
        The normalized draft state.
    """
    settings = payload.get("settings") or {}
    inner = settings.get("settings") or {}
    context = payload.get("context") or {}
    draft_order = payload.get("draftOrder") or {}
    countdown = payload.get("countdown") or {}

    my_team_id = str(context.get("managerId") or payload.get("myTeamId") or "")

    players: Dict[str, DraftPlayer] = {}
    for raw_player in payload.get("players") or []:
        player = parse_player(raw_player)
        if player is not None:
            players[player.player_id] = player

    teams: Dict[str, DraftTeam] = {}
    raw_teams = payload.get("teams") or {}
    entries = raw_teams.values() if isinstance(raw_teams, dict) else raw_teams
    for raw_team in entries:
        team_id = raw_team.get("id")
        if team_id is None:
            continue
        team_id = str(team_id)
        teams[team_id] = DraftTeam(
            team_id=team_id,
            name=str(raw_team.get("teamname") or f"Team {team_id}"),
            is_me=team_id == my_team_id,
        )

    picks: List[DraftPick] = []
    for raw_pick in payload.get("picks") or []:
        player_id = raw_pick.get("playerId")
        team_id = raw_pick.get("teamId")
        if player_id is None or team_id is None:
            continue
        picks.append(
            DraftPick(
                pick_number=_as_int(raw_pick.get("id")) or len(picks),
                player_id=str(player_id),
                team_id=str(team_id),
                cost=_as_float(raw_pick.get("cost")) or 0.0,
            )
        )
    picks.sort(key=lambda p: p.pick_number)

    # Manual overrides: players the user marked as drafted because the adapter
    # missed them. Team is deliberately unknown — we know the player is off the
    # board, not who holds him — so he leaves the pool without polluting any
    # roster's category totals.
    known = {pick.player_id for pick in picks}
    next_number = picks[-1].pick_number + 1 if picks else 0
    for raw_id in payload.get("manualPicks") or []:
        player_id = str(raw_id)
        if not player_id or player_id in known:
            continue
        known.add(player_id)
        picks.append(
            DraftPick(pick_number=next_number, player_id=player_id, team_id="")
        )
        next_number += 1

    return DraftState(
        league_id=str(settings.get("league_id") or context.get("leagueId") or ""),
        league_name=str(settings.get("name") or ""),
        season=str(inner.get("game_season") or ""),
        is_mock=bool(settings.get("is_mock_league")),
        is_auction=bool(inner.get("is_auction_draft")),
        num_teams=_as_int(settings.get("num_teams") or inner.get("max_teams")) or 0,
        pick_seconds=_as_int(settings.get("pickTime") or inner.get("draft_pick_duration")) or 0,
        seconds_remaining=_as_int(countdown.get("seconds")),
        draft_status=str((payload.get("draft") or {}).get("state") or ""),
        my_team_id=my_team_id,
        current_pick=_as_int(draft_order.get("currentPick")) or 0,
        current_team_id=str(draft_order.get("currentTeam") or ""),
        teams=teams,
        players=players,
        picks=picks,
        pick_order=_parse_pick_order(draft_order.get("order")),
        roster_slots=_parse_roster_slots(inner.get("roster_positions")),
        categories=stat_ids.parse_stat_categories(inner.get("stat_categories")),
        queue=[str(entry) for entry in (payload.get("queue") or [])],
    )
