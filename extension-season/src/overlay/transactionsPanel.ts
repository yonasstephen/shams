// The player form panel on Yahoo's league Transactions page: every player added, dropped or
// traded on the page, with the web app's waiver numbers (last N games or days, minutes, the
// minute trend), plus a minutes chip beside each name in Yahoo's own list.

import type { Feed } from "../feed/types";
import {
  FORM_WINDOWS,
  FORM_WINDOW_LABELS,
  type Aggregation,
  type FormWindow,
  type PlayerForm,
} from "../engine/playerForm";
import { SHAMS_ATTR, clearInjected, el, formatStat, statusBadge, toggle } from "./dom";
import { idleTone, statTone, toneClass, trendTone, type ColouredStat } from "./statColors";

const MARKER = "transactions-panel";
const CHIP_MARKER = "transactions-chip";

export type Move = "add" | "drop" | "trade";

/** One player in one of Yahoo's transaction rows. */
export interface TransactionPlayer {
  yahooId: string;
  name: string;
  teamAbbr: string;
  positions: string;
  injury: string;
  move: Move;
  /** How Yahoo words it: "Free Agent", "Waivers", "To Waivers", or the team a trade sent him to. */
  detail: string;
  fantasyTeam: string;
  when: string;
  link: HTMLAnchorElement;
}

export interface FormRow {
  order: number;
  player: TransactionPlayer;
  matched: boolean;
  form: PlayerForm;
}

export type SortColumn =
  | "order" | "name" | "games" | "minutes" | "trend" | "lastPlayed"
  | "fg_pct" | "ft_pct" | "threes" | "points" | "rebounds" | "assists" | "steals" | "blocks" | "turnovers";

export interface TransactionsState {
  window: FormWindow;
  aggregation: Aggregation;
  sort: { column: SortColumn; descending: boolean };
  today: string;
  feed: Feed | null;
  rows: FormRow[];
  status: { state: "loading" | "ready" | "error"; detail: string };
}

export interface TransactionsCallbacks {
  onWindowChange: (window: FormWindow) => void;
  onAggregationChange: (aggregation: Aggregation) => void;
  onSort: (column: SortColumn) => void;
  onRefresh: () => void;
}

// --- Reading Yahoo's table -------------------------------------------------------------

export function findTransactionTable(): HTMLTableElement | null {
  return document.querySelector<HTMLTableElement>("table.Tst-transaction-table");
}

const PLAYER_LINK = /sports\.yahoo\.com\/nba\/players\/(\d+)\/?$/;

/** Every player on the page, newest transaction first, in the order Yahoo lists them.
 *
 * Add/drop rows put one icon per player in the first cell ("Added Player", "Dropped
 * Player"), in the same order as the players. Trade rows say "Traded to" instead, and the
 * second row of a trade has no icon cell at all. */
export function readTransactions(table: HTMLTableElement): TransactionPlayer[] {
  const players: TransactionPlayer[] = [];

  for (const row of Array.from(table.querySelectorAll<HTMLTableRowElement>(":scope > tbody > tr"))) {
    const links = Array.from(row.querySelectorAll<HTMLAnchorElement>("a[href]")).filter((link) =>
      PLAYER_LINK.test(link.href),
    );
    if (!links.length) continue;

    const isTrade = /Traded to/i.test(row.textContent ?? "") || row.querySelector(".F-trade") !== null;
    const icons = Array.from(row.querySelectorAll("td:first-child [title]")).map((icon) => icon.getAttribute("title") ?? "");
    const teamCell = row.lastElementChild;
    const fantasyTeam = teamCell?.querySelector("span.Grid-u > a")?.textContent?.trim() ?? "";
    const when = teamCell?.querySelector(".F-timestamp")?.textContent?.trim() ?? "";

    links.forEach((link, index) => {
      const yahooId = PLAYER_LINK.exec(link.href)?.[1];
      if (!yahooId) return;
      const holder = link.closest("div, p") ?? link.parentElement;
      const [teamAbbr = "", positions = ""] = (holder?.querySelector(".F-position")?.textContent ?? "")
        .split(" - ")
        .map((part) => part.trim());
      const note = holder?.querySelector("h6")?.textContent?.trim() ?? "";

      let move: Move;
      if (isTrade) move = "trade";
      else if (icons[index] === "Dropped Player") move = "drop";
      else if (icons[index] === "Added Player") move = "add";
      else move = /^To /i.test(note) ? "drop" : "add";

      players.push({
        yahooId,
        name: link.textContent?.trim() ?? "",
        teamAbbr,
        positions,
        injury: holder?.querySelector(".F-injury")?.textContent?.trim() ?? "",
        move,
        detail: isTrade ? `to ${fantasyTeam}` : note,
        fantasyTeam,
        when,
        link,
      });
    });
  }

  return players;
}

// --- Formatting ------------------------------------------------------------------------

const MOVE_SYMBOLS: Record<Move, [string, string]> = {
  add: ["+", "Added"],
  drop: ["−", "Dropped"],
  trade: ["⇄", "Traded"],
};

const SHORT_WINDOW: Record<FormWindow, string> = {
  last: "last game",
  last3: "L3",
  last7: "L7",
  last7d: "7d",
  last14d: "14d",
  last30d: "30d",
  season: "season",
};

function perGame(state: TransactionsState): boolean {
  return state.aggregation === "avg" || state.window === "last";
}

function count(value: number, state: TransactionsState): string {
  return state.aggregation === "avg" && state.window !== "last" ? value.toFixed(1) : value.toFixed(0);
}

function signed(value: number): string {
  return `${value > 0 ? "+" : value < 0 ? "−" : "±"}${Math.abs(value).toFixed(1)}`;
}

function daysBetween(from: string, to: string): number {
  return Math.round((Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / 86_400_000);
}

function shortDate(iso: string): string {
  return new Date(`${iso}T00:00:00Z`).toLocaleDateString(undefined, { month: "short", day: "numeric", timeZone: "UTC" });
}

function trendTitle(form: PlayerForm): string {
  const trend = form.trend;
  if (!trend) return "No game with minutes in the feed's game log";
  return `${trend.last.toFixed(1)} min last game vs ${trend.priorAverage.toFixed(1)} over the three before`;
}

function statLineText(form: PlayerForm, state: TransactionsState): string {
  const stats = form.stats;
  if (!stats) return "";
  const parts = [
    `${count(stats.points, state)} pts`,
    `${count(stats.rebounds, state)} reb`,
    `${count(stats.assists, state)} ast`,
    `${count(stats.steals, state)} stl`,
    `${count(stats.blocks, state)} blk`,
    `${count(stats.threes, state)} 3pm`,
    `${count(stats.turnovers, state)} to`,
    `${formatStat(stats.fg_pct, true)} FG%`,
    `${formatStat(stats.ft_pct, true)} FT%`,
  ];
  return parts.join(" · ");
}

function sourceNote(form: PlayerForm, state: TransactionsState): string {
  if (form.source === "previous") return `last season (${state.feed?.meta.previous_season ?? "previous"})`;
  return "";
}

/** Why a matched player has no numbers in this window. */
function emptyReason(form: PlayerForm, state: TransactionsState): string {
  if (form.lastPlayed) return `no games in this window · last played ${shortDate(form.lastPlayed)}`;
  if (form.source === "none") return `no ${state.feed?.meta.season ?? "current-season"} games yet`;
  return `hasn't played in the last ${state.feed?.players.tail_days ?? 0} days`;
}

// --- Inline chips in Yahoo's list ------------------------------------------------------

function chip(entry: FormRow | undefined, state: TransactionsState): HTMLElement {
  if (!entry || !entry.matched) {
    return el("span", { class: "shams-inline shams-tone-dim", text: "no stats", title: "Not matched to NBA stats" });
  }

  const { form } = entry;
  const label = SHORT_WINDOW[state.window];
  if (!form.stats) {
    const text = form.source === "none" ? "no games yet" : `no games ${label}`;
    return el("span", { class: "shams-inline shams-tone-dim", text, title: emptyReason(form, state) });
  }

  const minutes = form.minutes === null ? null : `${count(form.minutes, state)}m`;
  const trend = form.trend ? signed(form.trend.delta) : null;
  const games = `${form.games} GP${form.dnp ? `, ${form.dnp} DNP` : ""}`;
  const source = sourceNote(form, state);
  const title = [
    `${FORM_WINDOW_LABELS[state.window]}${source ? `, ${source}` : ""} (${games})`,
    `${minutes ?? "–"} · ${statLineText(form, state)}`,
    `Minute trend: ${trendTitle(form)}`,
  ].join("\n");

  return el("span", { class: "shams-inline", title }, [
    el("span", { class: "shams-inline-window", text: source ? `'${(state.feed?.meta.previous_season ?? "").slice(2)}` : label }),
    el("span", {
      class: perGame(state) && form.minutes !== null ? toneClass(statTone("minutes", form.minutes)) : "",
      text: minutes ?? `${count(form.stats.points, state)} pts`,
    }),
    trend ? el("span", { class: toneClass(trendTone(form.trend?.delta ?? 0)), text: trend }) : null,
  ]);
}

export function renderInlineChips(players: TransactionPlayer[], rows: FormRow[], state: TransactionsState): void {
  clearInjected(CHIP_MARKER);
  const byId = new Map(rows.map((row) => [row.player.yahooId, row]));

  for (const player of players) {
    const node = chip(byId.get(player.yahooId), state);
    node.setAttribute(SHAMS_ATTR, CHIP_MARKER);
    const holder = player.link.closest("div, p") ?? player.link.parentElement;
    const after = holder?.querySelector(".F-injury") ?? holder?.querySelector(".F-position") ?? player.link;
    after.after(node);
  }
}

// --- The panel -------------------------------------------------------------------------

interface Column {
  key: SortColumn | null;
  label: string;
  title?: string;
  stat?: ColouredStat;
}

const STAT_COLUMNS: { key: Exclude<SortColumn, "order" | "name" | "games" | "minutes" | "trend" | "lastPlayed">; label: string }[] = [
  { key: "threes", label: "3PM" },
  { key: "points", label: "PTS" },
  { key: "rebounds", label: "REB" },
  { key: "assists", label: "AST" },
  { key: "steals", label: "STL" },
  { key: "blocks", label: "BLK" },
  { key: "turnovers", label: "TO" },
];

function sortValue(row: FormRow, column: SortColumn): number | string | null {
  const { form } = row;
  switch (column) {
    case "order":
      return row.order;
    case "name":
      return row.player.name;
    case "trend":
      return form.trend?.delta ?? null;
    case "lastPlayed":
      return form.lastPlayed;
    case "games":
      return form.stats ? form.games : null;
    case "minutes":
      return form.minutes;
    default:
      return form.stats ? form.stats[column] : null;
  }
}

/** Rows in the chosen order; rows without a number always sink, whichever way it sorts. */
export function sortRows(rows: FormRow[], sort: TransactionsState["sort"]): FormRow[] {
  const direction = sort.descending ? -1 : 1;
  return rows.slice().sort((a, b) => {
    const left = sortValue(a, sort.column);
    const right = sortValue(b, sort.column);
    if (left === null || right === null) {
      if (left === right) return a.order - b.order;
      return left === null ? 1 : -1;
    }
    if (left < right) return -direction;
    if (left > right) return direction;
    return a.order - b.order;
  });
}

function header(column: Column, state: TransactionsState, callbacks: TransactionsCallbacks): HTMLElement {
  const active = column.key !== null && state.sort.column === column.key;
  const arrow = active ? (state.sort.descending ? " ▼" : " ▲") : "";
  const th = el("th", {
    class: [column.key === "name" ? "shams-name" : "", column.key ? "shams-sortable" : ""].join(" ").trim(),
    text: `${column.label}${arrow}`,
    title: column.title ?? "",
  });
  if (column.key) {
    const key = column.key;
    th.addEventListener("click", () => callbacks.onSort(key));
  }
  return th;
}

function toned(text: string, stat: ColouredStat, value: number, state: TransactionsState): HTMLElement {
  return el("td", { class: perGame(state) ? toneClass(statTone(stat, value)) : "", text });
}

function playerRow(row: FormRow, state: TransactionsState, columnCount: number): HTMLElement {
  const { player, form } = row;
  const [symbol, verb] = MOVE_SYMBOLS[player.move];
  const moveTitle = [`${verb}${player.move === "trade" ? "" : ` by ${player.fantasyTeam}`}`, player.detail, player.when]
    .filter(Boolean)
    .join(" · ");

  const nameCell = el("td", { class: "shams-name" }, [
    el("span", { text: player.name }),
    el("span", { class: "shams-source", text: ` ${player.teamAbbr}` }),
    player.injury ? el("span", { class: "shams-chip shams-chip-il", text: player.injury }) : null,
    form.source === "previous"
      ? el("span", { class: "shams-source", text: ` (${state.feed?.meta.previous_season ?? "last season"})`, title: "No games this season yet: last season's averages" })
      : null,
  ]);
  const moveCell = el("td", { class: "shams-name", title: moveTitle }, [
    el("span", { class: `shams-move shams-move-${player.move}`, text: symbol }),
    el("span", { class: "shams-move-team", text: player.fantasyTeam }),
  ]);

  const stats = form.stats;
  if (!row.matched || !stats) {
    const reason = row.matched ? emptyReason(form, state) : "not matched to NBA stats";
    return el("tr", { class: "shams-injured" }, [
      nameCell,
      moveCell,
      el("td", { class: "shams-split", text: reason, attrs: { colspan: String(columnCount - 2) } }),
    ]);
  }

  const lastPlayedCell = form.lastPlayed
    ? el("td", {
        class: toneClass(idleTone(daysBetween(form.lastPlayed, state.today))),
        text: shortDate(form.lastPlayed),
        title: form.lastPlayed,
      })
    : el("td", { class: "shams-tone-dim", text: "–" });

  return el("tr", {}, [
    nameCell,
    moveCell,
    el("td", { title: form.dnp === null ? "" : `${form.games - form.dnp} played, ${form.dnp} sat` }, [
      el("span", { text: String(form.games) }),
      form.dnp ? el("span", { class: "shams-source", text: ` ${form.dnp} DNP` }) : null,
    ]),
    form.minutes === null
      ? el("td", { class: "shams-tone-dim", text: "–", title: "This feed has no season minutes yet" })
      : toned(count(form.minutes, state), "minutes", form.minutes, state),
    form.trend
      ? el("td", { class: toneClass(trendTone(form.trend.delta)), text: signed(form.trend.delta), title: trendTitle(form) })
      : el("td", { class: "shams-tone-dim", text: "–", title: trendTitle(form) }),
    el("td", { class: "shams-split", text: `${count(stats.fgm, state)}/${count(stats.fga, state)}` }),
    stats.fga > 0 ? toned(formatStat(stats.fg_pct, true), "fg_pct", stats.fg_pct, state) : el("td", { class: "shams-tone-dim", text: "–" }),
    el("td", { class: "shams-split", text: `${count(stats.ftm, state)}/${count(stats.fta, state)}` }),
    stats.fta > 0 ? toned(formatStat(stats.ft_pct, true), "ft_pct", stats.ft_pct, state) : el("td", { class: "shams-tone-dim", text: "–" }),
    ...STAT_COLUMNS.map((column) => toned(count(stats[column.key], state), column.key, stats[column.key], state)),
    lastPlayedCell,
  ]);
}

function footnote(state: TransactionsState): string {
  const days = state.feed?.players.tail_days ?? 0;
  const basis = `${FORM_WINDOW_LABELS[state.window]}, ${state.aggregation === "avg" ? "per game" : "totals"}`;
  return (
    `${basis}. As in the web app, a game he sat counts as a game (DNP), so averages include his zeros. ` +
    `Trend: minutes in his last game against the three before it. ` +
    `Game logs reach back ${days} days, so a player out longer than that comes up short on games.`
  );
}

export function renderTransactionsPanel(state: TransactionsState, callbacks: TransactionsCallbacks): void {
  const table = findTransactionTable();
  if (!table) return;
  const anchor = table.closest(".Mod") ?? table;

  clearInjected(MARKER);

  const panel = el("div", { class: "shams-panel" });
  panel.setAttribute(SHAMS_ATTR, MARKER);

  const windowSelect = el("select", { class: "shams-select" }) as HTMLSelectElement;
  for (const window of FORM_WINDOWS) {
    const option = el("option", { text: FORM_WINDOW_LABELS[window] }) as HTMLOptionElement;
    option.value = window;
    option.selected = window === state.window;
    windowSelect.appendChild(option);
  }
  windowSelect.addEventListener("change", () => callbacks.onWindowChange(windowSelect.value as FormWindow));

  const refresh = el("button", { class: "shams-button", text: "Refresh" });
  refresh.addEventListener("click", () => callbacks.onRefresh());

  const feedAge = state.feed
    ? `feed ${state.feed.meta.season} · ${new Date(state.feed.meta.generated_at).toLocaleDateString()}`
    : "no feed";

  panel.appendChild(
    el("div", { class: "shams-panel-head" }, [
      el("span", { class: "shams-title", text: "Shams player form" }),
      windowSelect,
      toggle<Aggregation>([["avg", "Average"], ["sum", "Total"]], state.aggregation, callbacks.onAggregationChange),
      refresh,
      el("span", { class: "shams-spacer" }),
      statusBadge(state.status.state, state.status.detail),
      el("span", { class: "shams-badge", text: feedAge }),
    ]),
  );

  if (state.feed && state.feed.meta.counts["players_with_games"] === 0) {
    panel.appendChild(
      el("div", {
        class: "shams-summary",
        text:
          `No ${state.feed.meta.season} games in the feed yet. The game windows fill in once the season is ` +
          `under way and the feed rebuilds; until then, Season shows ${state.feed.meta.previous_season}.`,
      }),
    );
  }

  if (!state.rows.length) {
    panel.appendChild(el("div", { class: "shams-empty", text: state.status.state === "ready" ? "No players on this page." : state.status.detail }));
    anchor.parentElement?.insertBefore(panel, anchor);
    return;
  }

  const columns: Column[] = [
    { key: "name", label: "Player" },
    { key: "order", label: "Move", title: "Who made the move; sorts back to Yahoo's order" },
    { key: "games", label: "GP", title: "Games in the window, including ones he sat" },
    { key: "minutes", label: "MIN" },
    { key: "trend", label: "Trend", title: "Minutes in his last game against the three before it" },
    { key: null, label: "FGM/A" },
    { key: "fg_pct", label: "FG%" },
    { key: null, label: "FTM/A" },
    { key: "ft_pct", label: "FT%" },
    ...STAT_COLUMNS.map((column) => ({ key: column.key, label: column.label })),
    { key: "lastPlayed", label: "Last", title: "His most recent game with minutes" },
  ];

  const formTable = el("table", { class: "shams-table shams-form-table" });
  formTable.appendChild(el("thead", {}, [el("tr", {}, columns.map((column) => header(column, state, callbacks)))]));
  formTable.appendChild(el("tbody", {}, sortRows(state.rows, state.sort).map((row) => playerRow(row, state, columns.length))));

  panel.appendChild(el("div", { class: "shams-scroll" }, [formTable]));
  panel.appendChild(el("div", { class: "shams-sub", text: footnote(state) }));

  anchor.parentElement?.insertBefore(panel, anchor);
}
