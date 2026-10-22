// League Transactions page: recent form for every player added, dropped or traded, the way
// the web app's waiver table shows it. Everything comes from the page and the feed; no
// Yahoo API call is needed, because the page already names each player and his Yahoo id.

import { todayIso } from "./context";
import { getFeed } from "../feed/client";
import type { Feed } from "../feed/types";
import { whenPresent } from "../overlay/dom";
import {
  findTransactionTable,
  readTransactions,
  renderInlineChips,
  renderTransactionsPanel,
  type FormRow,
  type SortColumn,
  type TransactionPlayer,
  type TransactionsState,
} from "../overlay/transactionsPanel";
import { FORM_WINDOWS, playerForm, type Aggregation, type FormWindow } from "../engine/playerForm";
import { resolveNbaId } from "../engine/playerIdentity";

const STORAGE_KEY = "shams.transactions";

const state: TransactionsState = {
  window: "last7d",
  aggregation: "avg",
  sort: { column: "order", descending: false },
  today: todayIso(),
  feed: null,
  rows: [],
  status: { state: "loading", detail: "loading…" },
};

let players: TransactionPlayer[] = [];

function persist(): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ window: state.window, aggregation: state.aggregation }));
  } catch {
    // Private windows and blocked site data: the choice just won't persist.
  }
}

function restore(): void {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}") as Partial<TransactionsState>;
    if (saved.window && FORM_WINDOWS.includes(saved.window)) state.window = saved.window;
    if (saved.aggregation === "avg" || saved.aggregation === "sum") state.aggregation = saved.aggregation;
  } catch {
    // Storage unavailable or corrupt: the defaults are fine.
  }
}

/** One row per player, at his most recent move on the page. */
function computeRows(feed: Feed): FormRow[] {
  const seen = new Set<string>();
  const rows: FormRow[] = [];
  for (const player of players) {
    if (seen.has(player.yahooId)) continue;
    seen.add(player.yahooId);

    const nbaId = resolveNbaId(feed.index, player.yahooId, player.name);
    const form = playerForm({
      entry: nbaId ? feed.players.players[nbaId] : undefined,
      previous: nbaId ? feed.playersPrev.players[nbaId] : undefined,
      window: state.window,
      aggregation: state.aggregation,
      today: state.today,
    });
    rows.push({ order: rows.length, player, matched: nbaId !== null, form });
  }
  return rows;
}

function render(): void {
  renderTransactionsPanel(state, {
    onWindowChange: (window: FormWindow) => {
      state.window = window;
      persist();
      recompute();
    },
    onAggregationChange: (aggregation: Aggregation) => {
      state.aggregation = aggregation;
      persist();
      recompute();
    },
    onSort: (column: SortColumn) => {
      const same = state.sort.column === column;
      // Fewer turnovers is better, and names and Yahoo's order read top-down.
      const ascendingFirst = column === "turnovers" || column === "name" || column === "order";
      state.sort = { column, descending: same ? !state.sort.descending : !ascendingFirst };
      render();
    },
    onRefresh: () => void refresh(true),
  });
  renderInlineChips(players, state.rows, state);
}

function recompute(): void {
  if (!state.feed) return;
  state.today = todayIso();
  state.rows = computeRows(state.feed);
  const unmatched = state.rows.filter((row) => !row.matched).length;
  state.status = {
    state: "ready",
    detail: `${state.rows.length} players${unmatched ? ` · ${unmatched} unmatched` : ""}`,
  };
  render();
}

async function refresh(force: boolean): Promise<void> {
  state.status = { state: "loading", detail: "loading…" };
  render();

  try {
    state.feed = await getFeed(force);
    recompute();
  } catch (error) {
    state.status = { state: "error", detail: error instanceof Error ? error.message : String(error) };
    render();
  }
}

async function run(): Promise<void> {
  const table = await whenPresent(() => findTransactionTable());
  if (!(table instanceof HTMLTableElement)) return;

  players = readTransactions(table);
  restore();
  await refresh(false);
}

run().catch((error: unknown) => {
  console.warn("[shams] transactions overlay failed:", error);
});
