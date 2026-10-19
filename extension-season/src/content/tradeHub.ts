// Trade Hub page: the trade insights panel — every team's strengths and weaknesses by
// category, and the league grid. See docs/trade-insights.md.

import { loadPageContext, todayIso, type PageContext } from "./context";
import { whenPresent } from "../overlay/dom";
import {
  PROFILE_MODES,
  findTradeHubRoot,
  renderTradeHubPanel,
  type GridBasis,
  type TradeHubState,
  type TradeHubView,
} from "../overlay/tradeHubPanel";
import { profileLeague, type ProfileMode } from "../engine/teamProfile";
import { fetchLeagueRosters } from "../yahoo/client";
import type { LeagueRoster } from "../yahoo/types";

const STORAGE_KEY = "shams.tradeHub";

const state: TradeHubState = {
  mode: "ros",
  view: "profile",
  basis: "categories",
  selectedTeamKey: null,
  userTeamKey: null,
  today: todayIso(),
  tradeEndDate: "",
  feed: null,
  profile: null,
  status: { state: "loading", detail: "loading…" },
};

let context: PageContext | null = null;
let rosters: LeagueRoster[] | null = null;

function persist(): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ mode: state.mode, view: state.view, basis: state.basis }));
  } catch {
    // Private windows and blocked site data: the choice just won't persist.
  }
}

function restore(): void {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}") as Partial<TradeHubState>;
    if (saved.mode && PROFILE_MODES.includes(saved.mode)) state.mode = saved.mode;
    if (saved.view === "profile" || saved.view === "grid") state.view = saved.view;
    if (saved.basis === "categories" || saved.basis === "slots") state.basis = saved.basis;
  } catch {
    // Storage unavailable or corrupt: the defaults are fine.
  }
}

function render(): void {
  renderTradeHubPanel(state, {
    onModeChange: (mode: ProfileMode) => {
      state.mode = mode;
      persist();
      recompute();
    },
    onViewChange: (view: TradeHubView) => {
      state.view = view;
      persist();
      render();
    },
    onBasisChange: (basis: GridBasis) => {
      state.basis = basis;
      persist();
      render();
    },
    onTeamChange: (teamKey: string) => {
      state.selectedTeamKey = teamKey;
      render();
    },
    onRefresh: () => void refresh(true),
  });
}

/** Re-run the league profile from what is already loaded — a mode change needs no fetch. */
function recompute(): void {
  if (!context || !rosters) return;
  const { settings, feed } = context;
  state.today = todayIso();

  // Preseason, the horizon starts on opening night; in season, today.
  const start = settings.startDate && settings.startDate > state.today ? settings.startDate : state.today;
  const end = settings.endDate || start;

  const rosterPositions = settings.rosterPositions.flatMap((slot) =>
    Array.from({ length: slot.count }, () => slot.position),
  );

  state.profile = profileLeague({
    feed,
    categories: settings.statCategories,
    rosterPositions,
    rosters,
    today: state.today,
    horizonStart: start,
    horizonEnd: end,
    mode: state.mode,
  });
  state.status = { state: "ready", detail: `${rosters.length} teams · through ${end}` };
  render();
}

async function refresh(force: boolean): Promise<void> {
  state.status = { state: "loading", detail: "loading…" };
  render();

  try {
    context = await loadPageContext(force);
    state.feed = context.feed;
    state.userTeamKey = context.userTeamKey;
    state.tradeEndDate = context.settings.tradeEndDate;
    rosters = await fetchLeagueRosters(context.leagueKey);
    if (!rosters.length) throw new Error("Yahoo returned no rosters for this league");
    recompute();
  } catch (error) {
    state.profile = null;
    state.status = { state: "error", detail: error instanceof Error ? error.message : String(error) };
    render();
  }
}

async function run(): Promise<void> {
  const anchor = await whenPresent(() => findTradeHubRoot());
  if (!anchor) return;

  restore();
  await refresh(false);
}

run().catch((error: unknown) => {
  console.warn("[shams] trade hub overlay failed:", error);
});
