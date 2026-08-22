"""Live draft assistant API endpoints.

Deliberately **unauthenticated and stateless**. Everything needed to produce a
board — the player pool, projections, league settings, scoring categories and
pick history — arrives in the POST body from the extension, which read it out of
Yahoo's own draft-room store. That means:

- no Yahoo API call sits between a pick and a recommendation,
- no OAuth token can expire mid-draft,
- the extension can push the *whole* state every tick and we recompute from
  scratch, which makes refreshes, reconnects and out-of-order messages harmless.
"""

import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from typing import Dict, Optional

from fastapi import APIRouter, HTTPException

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from app.models import DraftBoardResponse, DraftStateRequest
from app.models.draft import (
    CategorySupplyModel,
    PuntVerdictModel,
    RecommendationModel,
    RosterEntry,
)

from tools.draft import recommender
from tools.draft.draft_state import DraftState, parse_draft_state
from tools.draft.punt_detector import PuntVerdict
from tools.draft.recommender import DraftBoard, Recommendation
from tools.draft.scarcity import CategorySupply

logger = logging.getLogger(__name__)

router = APIRouter()

#: Set SHAMS_DRAFT_CAPTURE_DIR to record every payload the extension sends.
#: The draft room's own CSP blocks the page from posting anywhere, so this is
#: the practical way to collect real fixtures — run a mock draft with it set and
#: you get a directory of genuine snapshots to develop and test against offline.
_CAPTURE_DIR = os.getenv("SHAMS_DRAFT_CAPTURE_DIR", "")


def _capture(payload: dict) -> None:
    """Persist a raw payload for offline replay, if capture is enabled."""
    if not _CAPTURE_DIR:
        return
    try:
        directory = Path(_CAPTURE_DIR).expanduser()
        directory.mkdir(parents=True, exist_ok=True)
        pick = (payload.get("draftOrder") or {}).get("currentPick", "x")
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = directory / f"draft-{stamp}-pick{pick}.json"
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
    except OSError as exc:
        # Capture is a developer convenience; never let it break a live draft.
        logger.warning("Draft payload capture failed: %s", exc)


def _recommendation_model(rec: Recommendation) -> RecommendationModel:
    """Convert a recommendation to its API model."""
    return RecommendationModel(
        player_id=rec.player_id,
        name=rec.name,
        positions=rec.positions,
        nba_team=rec.nba_team,
        injury=rec.injury,
        total_value=round(rec.total_value, 4),
        marginal_value=round(rec.marginal_value, 4),
        score=round(rec.score, 4),
        category_z={name: round(z, 4) for name, z in rec.category_z.items()},
        standings_delta=(
            None if rec.standings_delta is None else round(rec.standings_delta, 4)
        ),
        survival=None if rec.survival is None else round(rec.survival, 4),
        average_pick=rec.average_pick,
        value_gap=None if rec.value_gap is None else round(rec.value_gap, 2),
        gap_label=rec.gap_label,
        reason=rec.reason,
    )


def _supply_model(supply: CategorySupply) -> CategorySupplyModel:
    """Convert a category supply entry to its API model."""
    return CategorySupplyModel(
        name=supply.name,
        display_name=supply.display_name,
        my_total=round(supply.my_total, 3),
        my_rank=supply.my_rank,
        league_mean=round(supply.league_mean, 3),
        deficit=round(supply.deficit, 3),
        is_weakness=supply.is_weakness,
        elite_remaining=supply.elite_remaining,
        starter_remaining=supply.starter_remaining,
        best_available=round(supply.best_available, 3),
        teams_below_mean=supply.teams_below_mean,
        crunch=round(supply.crunch, 3),
        is_supply_crunch=supply.is_supply_crunch,
        elite_surviving=round(supply.elite_surviving, 2),
        cliff_in_picks=supply.cliff_in_picks,
        cliff_drop=round(supply.cliff_drop, 3),
        summary=supply.summary(),
    )


def _punt_model(
    verdict: PuntVerdict, display_names: Optional[Dict[str, str]] = None
) -> PuntVerdictModel:
    """Convert a punt verdict to its API model.

    The label is rebuilt with the league's own category names — "punt FG%" reads
    at a glance, "punt fg_pct" is an internal identifier leaking into the UI.
    """
    names = display_names or {}
    if verdict.categories:
        pretty = " + ".join(sorted(names.get(c, c) for c in verdict.categories))
        label = f"punt {pretty}"
    else:
        label = "no punt"

    return PuntVerdictModel(
        categories=sorted(verdict.categories),
        label=label,
        category_wins=round(verdict.category_wins, 3),
        baseline_wins=round(verdict.baseline_wins, 3),
        gain=round(verdict.gain, 3),
        is_recommended=verdict.is_recommended,
    )


def _warnings(state: DraftState) -> list:
    """Surface anything that will quietly degrade the recommendations.

    A draft is the worst possible time to silently return a plausible-looking
    board built on missing data, so these go in the response for the panel to
    display.
    """
    issues = []
    if not state.categories:
        issues.append("No scoring categories found — check the league settings slice.")
    if not state.players:
        issues.append("No players in the payload.")
    if not state.pick_order:
        issues.append("No draft order — survival and pick timing are unavailable.")
    if not state.my_team_id:
        issues.append("Could not identify your team; roster analysis is disabled.")

    manual = sum(1 for pick in state.picks if not pick.team_id)
    if manual:
        issues.append(f"{manual} pick(s) marked drafted by hand.")

    unprojected = sum(1 for p in state.players.values() if not p.has_projection)
    if state.players and unprojected > len(state.players) * 0.5:
        issues.append(
            f"{unprojected} of {len(state.players)} players have no projection."
        )
    return issues


def _board_response(state: DraftState, board: DraftBoard, compute_ms: float) -> DraftBoardResponse:
    """Assemble the API response."""
    display_names = {c.name: c.display_name for c in state.categories}
    return DraftBoardResponse(
        headline=_recommendation_model(board.headline) if board.headline else None,
        alternatives=[_recommendation_model(r) for r in board.alternatives],
        board=[_recommendation_model(r) for r in board.board],
        supply=[_supply_model(s) for s in board.supply],
        heat_map={name: round(value, 3) for name, value in board.heat_map.items()},
        punt=_punt_model(board.punt, display_names) if board.punt else None,
        punt_options=[_punt_model(v, display_names) for v in board.punt_options],
        my_roster=[
            RosterEntry(
                player_id=p.player_id,
                name=p.name,
                positions=list(p.positions),
                nba_team=p.nba_team,
                injury=p.injury,
            )
            for p in board.my_roster
        ],
        positional_gaps=board.positional_gaps,
        schedule_available=board.schedule_available,
        picks_until_my_turn=board.picks_until_my_turn,
        is_my_turn=board.is_my_turn,
        seconds_remaining=board.seconds_remaining,
        current_pick=board.current_pick,
        projected_category_wins=round(board.projected_category_wins, 3),
        league_name=state.league_name,
        is_mock=state.is_mock,
        num_teams=state.num_teams,
        total_rounds=state.total_rounds,
        players_seen=len(state.players),
        picks_seen=len(state.picks),
        compute_ms=round(compute_ms, 2),
        warnings=_warnings(state),
    )


@router.post("/state", response_model=DraftBoardResponse)
def analyze_draft_state(payload: DraftStateRequest) -> DraftBoardResponse:
    """Analyze a draft-room snapshot and return the board.

    Idempotent by design: the extension sends the complete state on every change
    and this recomputes from scratch, so nothing is lost if a message is dropped,
    duplicated, delivered out of order, or the draft room is refreshed.
    """
    started = time.perf_counter()
    try:
        raw = payload.model_dump(exclude_none=True)
        _capture(raw)
        state = parse_draft_state(raw)
        board = recommender.recommend(state)
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("Draft analysis failed")
        raise HTTPException(status_code=500, detail=f"Draft analysis failed: {exc}") from exc

    compute_ms = (time.perf_counter() - started) * 1000.0
    if compute_ms > 500:
        logger.warning("Slow draft analysis: %.0fms with %d players", compute_ms, len(state.players))

    return _board_response(state, board, compute_ms)


@router.get("/health")
def draft_health() -> dict:
    """Readiness check the extension can call before the draft starts.

    Worth its own endpoint: the failure everyone hits is discovering at pick 1
    that the backend was never running.
    """
    return {"status": "ready", "engine": "shams-draft"}
