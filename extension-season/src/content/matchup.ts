// Matchup page: the projection panel, per-player contributions and best adds.

import { loadMatchup, loadPageContext, loadRosterByDate, resolveTeamKey, type PageContext } from "./context";
import { findTotalsTable, renderMatchupPanel, type PanelState } from "../overlay/matchupPanel";
import { whenPresent } from "../overlay/dom";
import { projectMatchup, type ProjectionResult } from "../engine/project";
import { rankAdds } from "../engine/adds";
import { fetchFreeAgents } from "../yahoo/client";
import type { ProjectionMode } from "../engine/statWindows";

const MODE_KEY = "shams.projectionMode";

const state: PanelState = {
  mode: "season",
  feed: null,
  projection: null,
  adds: null,
  status: { state: "loading", detail: "loading…" },
};

function render(): void {
  renderMatchupPanel(state, {
    onModeChange: (mode) => {
      state.mode = mode;
      try {
        localStorage.setItem(MODE_KEY, mode);
      } catch {
        // Private windows and blocked site data: the choice just won't persist.
      }
      void refresh(false);
    },
    onRefresh: () => void refresh(true),
  });
}

function weekFromUrl(): number | undefined {
  const week = new URLSearchParams(location.search).get("week");
  return week && /^\d+$/.test(week) ? Number(week) : undefined;
}

async function build(context: PageContext): Promise<{ projection: ProjectionResult; userIndex: number }> {
  const teamKey = resolveTeamKey(context);
  if (!teamKey) throw new Error("could not work out which team this matchup is for");

  const matchup = await loadMatchup(teamKey, weekFromUrl());
  if (matchup.teams.length < 2) throw new Error("matchup has fewer than two teams");

  const today = context.today;
  const [teamA, teamB] = matchup.teams as [(typeof matchup.teams)[0], (typeof matchup.teams)[0]];
  const [rosterA, rosterB] = await Promise.all([
    loadRosterByDate(teamA.teamKey, matchup.weekStart, matchup.weekEnd, today),
    loadRosterByDate(teamB.teamKey, matchup.weekStart, matchup.weekEnd, today),
  ]);

  const rosterPositions = context.settings.rosterPositions.flatMap((slot) =>
    Array.from({ length: slot.count }, () => slot.position),
  );

  const projection = projectMatchup({
    feed: context.feed,
    categories: context.settings.statCategories,
    rosterPositions,
    weekStart: matchup.weekStart,
    weekEnd: matchup.weekEnd,
    today,
    mode: state.mode,
    teams: [
      { teamKey: teamA.teamKey, name: teamA.name, rosterByDate: rosterA, weekTotals: teamA.stats, optimize: false },
      { teamKey: teamB.teamKey, name: teamB.name, rosterByDate: rosterB, weekTotals: teamB.stats, optimize: false },
    ],
  });

  const userIndex = projection.teams.findIndex((team) => team.teamKey === (context.userTeamKey ?? teamKey));
  return { projection, userIndex: userIndex >= 0 ? userIndex : 0 };
}

async function refresh(force: boolean): Promise<void> {
  state.status = { state: "loading", detail: "loading…" };
  render();

  try {
    const context = await loadPageContext(force);
    state.feed = context.feed;

    const { projection, userIndex } = await build(context);
    state.projection = projection;
    state.status = { state: "ready", detail: `week ${projection.weekStart.slice(5)} – ${projection.weekEnd.slice(5)}` };
    render();

    // Adds depend on the projection, so they land as a second paint rather than
    // holding up the numbers people came for.
    try {
      const freeAgents = await fetchFreeAgents(context.leagueKey, 60);
      state.adds = rankAdds({
        feed: context.feed,
        categories: context.settings.statCategories,
        user: projection.teams[userIndex === 1 ? 1 : 0],
        opponent: projection.teams[userIndex === 1 ? 0 : 1],
        freeAgents,
        weekStart: projection.weekStart,
        weekEnd: projection.weekEnd,
        today: context.today,
        mode: state.mode,
      });
      render();
    } catch (error) {
      console.warn("[shams] best adds unavailable:", error);
    }
  } catch (error) {
    state.projection = null;
    state.status = {
      state: "error",
      detail: error instanceof Error ? error.message : String(error),
    };
    render();
  }
}

async function run(): Promise<void> {
  const anchor = await whenPresent(() => findTotalsTable());
  if (!anchor) return;

  try {
    const stored = localStorage.getItem(MODE_KEY);
    if (stored) state.mode = stored as ProjectionMode;
  } catch {
    // Storage unavailable — season averages is a fine default.
  }

  await refresh(false);
}

run().catch((error: unknown) => {
  console.warn("[shams] matchup overlay failed:", error);
});
