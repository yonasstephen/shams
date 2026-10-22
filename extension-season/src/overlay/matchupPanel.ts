// The matchup projection panel: totals per category, the projected category score, and
// per-player contributions split into banked and remaining.

import type { Feed } from "../feed/types";
import type { StatCategory } from "../yahoo/types";
import type { AddCandidate } from "../engine/adds";
import type { ProjectionResult, TeamProjection, Totals } from "../engine/project";
import { MODE_LABELS, PROJECTION_MODES, type ProjectionMode } from "../engine/statWindows";
import { SHAMS_ATTR, clearInjected, el, formatStat, gamesClass, statusBadge } from "./dom";

const MARKER = "matchup-panel";

export interface PanelCallbacks {
  onModeChange: (mode: ProjectionMode) => void;
  onRefresh: () => void;
}

export interface PanelState {
  mode: ProjectionMode;
  feed: Feed | null;
  projection: ProjectionResult | null;
  adds: AddCandidate[] | null;
  status: { state: "loading" | "ready" | "error"; detail: string };
}

/** Yahoo's own week-totals table, which the panel is inserted beneath. */
export function findTotalsTable(): HTMLTableElement | null {
  const tables = Array.from(document.querySelectorAll<HTMLTableElement>("table.Datatable"));
  return (
    tables.find((table) => {
      if (table.closest(`[${SHAMS_ATTR}]`)) return false;
      const headers = Array.from(table.querySelectorAll("thead th")).map((th) => (th.textContent ?? "").trim());
      if (headers[0] !== "Team") return false;
      // WZRD injects a look-alike table; its giveaway is a Win % column.
      return !headers.includes("Win %");
    }) ?? null
  );
}

function scoreCell(points: { win: number; loss: number; tie: number }): string {
  return points.tie > 0 ? `${points.win}-${points.loss}-${points.tie}` : `${points.win}-${points.loss}`;
}

function comparisonClass(
  category: StatCategory,
  mine: number,
  theirs: number,
): string {
  if (Math.abs(mine - theirs) < 0.001) return "shams-tie";
  const lowerIsBetter = category.sortOrder === "0";
  const winning = lowerIsBetter ? mine < theirs : mine > theirs;
  return winning ? "shams-win" : "shams-loss";
}

function totalsRow(
  team: TeamProjection,
  opponent: Totals,
  categories: StatCategory[],
  points: { win: number; loss: number; tie: number },
): HTMLTableRowElement {
  const row = el("tr");
  row.appendChild(el("td", { class: "shams-name", text: team.name }));

  for (const category of categories) {
    if (category.isDisplayOnly) continue;
    const isPercentage = category.displayName.includes("%");
    const mine = team.combined[category.statId] ?? 0;
    const theirs = opponent[category.statId] ?? 0;

    const cell = el("td", { class: comparisonClass(category, mine, theirs) });
    cell.appendChild(el("div", { text: formatStat(mine, isPercentage) }));
    if (!isPercentage) {
      cell.appendChild(
        el("div", {
          class: "shams-split",
          text: `${formatStat(team.current[category.statId] ?? 0, false)} + ${formatStat(team.remaining[category.statId] ?? 0, false)}`,
          title: "banked this week + projected for remaining games",
        }),
      );
    }
    row.appendChild(cell);
  }

  row.appendChild(el("td", { class: "shams-score", text: scoreCell(points) }));
  return row;
}

function playerList(team: TeamProjection, categories: StatCategory[], heading: string): HTMLElement {
  const table = el("table", { class: "shams-table" });
  const head = el("tr", {}, [
    el("th", { class: "shams-name", text: "Player" }),
    el("th", { text: "G" }),
    ...categories.filter((c) => !c.isDisplayOnly).map((c) => el("th", { text: c.displayName })),
  ]);
  table.appendChild(el("thead", {}, [head]));

  const body = el("tbody");
  const sorted = team.players
    .slice()
    .sort((a, b) => b.remainingGames - a.remainingGames || a.name.localeCompare(b.name));

  for (const player of sorted) {
    const row = el("tr", {}, [
      el("td", { class: "shams-name" }, [
        el("span", { text: player.name }),
        player.source === "projection" || player.source === "previous"
          ? el("span", {
              class: "shams-source",
              text: player.source === "projection" ? " (proj)" : " (last yr)",
              title:
                player.source === "projection"
                  ? "No current-season sample yet — using the preseason projection"
                  : "No current-season sample yet — using last season's averages",
            })
          : null,
      ]),
      el("td", {}, [
        el("span", {
          class: gamesClass(player.remainingGames),
          text: `${player.remainingGames}/${player.totalGames}`,
        }),
      ]),
      ...categories
        .filter((c) => !c.isDisplayOnly)
        .map((c) => {
          const isPercentage = c.displayName.includes("%");
          const banked = player.current[c.statId] ?? 0;
          const projected = player.projected[c.statId] ?? 0;
          const value = isPercentage ? projected : banked + projected;
          return el("td", { text: formatStat(value, isPercentage) });
        }),
    ]);
    body.appendChild(row);
  }
  table.appendChild(body);

  return el("div", { class: "shams-column" }, [el("h4", { text: heading }), table]);
}

function addsList(adds: AddCandidate[]): HTMLElement {
  if (!adds.length) {
    return el("div", { class: "shams-empty", text: "No free agent improves a category this week." });
  }

  const table = el("table", { class: "shams-table" });
  table.appendChild(
    el("thead", {}, [
      el("tr", {}, [
        el("th", { class: "shams-name", text: "Best adds" }),
        el("th", { text: "Team" }),
        el("th", { text: "G left" }),
        el("th", { text: "Cats" }),
        el("th", { class: "shams-name", text: "Flips" }),
        el("th", { class: "shams-name", text: "Costs" }),
      ]),
    ]),
  );

  const body = el("tbody");
  for (const add of adds) {
    body.appendChild(
      el("tr", {}, [
        el("td", { class: "shams-name", text: add.name }),
        el("td", { text: add.teamAbbr }),
        el("td", {}, [el("span", { class: gamesClass(add.remainingGames), text: String(add.remainingGames) })]),
        el("td", {
          class: add.categoriesGained > 0 ? "shams-win" : "",
          text: add.categoriesGained > 0 ? `+${add.categoriesGained}` : String(add.categoriesGained),
        }),
        el("td", { class: "shams-name", text: add.flips.join(", ") || "—" }),
        el("td", { class: add.costs.length ? "shams-name shams-loss" : "shams-name", text: add.costs.join(", ") || "—" }),
      ]),
    );
  }
  table.appendChild(body);
  return table;
}

export function renderMatchupPanel(state: PanelState, callbacks: PanelCallbacks): void {
  const anchor = findTotalsTable();
  if (!anchor) return;

  clearInjected(MARKER);

  const panel = el("div", { class: "shams-panel" });
  panel.setAttribute(SHAMS_ATTR, MARKER);

  const modeSelect = el("select", { class: "shams-select" }) as HTMLSelectElement;
  for (const mode of PROJECTION_MODES) {
    const option = el("option", { text: MODE_LABELS[mode] }) as HTMLOptionElement;
    option.value = mode;
    option.selected = mode === state.mode;
    modeSelect.appendChild(option);
  }
  modeSelect.addEventListener("change", () => callbacks.onModeChange(modeSelect.value as ProjectionMode));

  const refresh = el("button", { class: "shams-button", text: "Refresh" });
  refresh.addEventListener("click", () => callbacks.onRefresh());

  const feedAge = state.feed
    ? `feed ${state.feed.meta.season} · ${new Date(state.feed.meta.generated_at).toLocaleDateString()}`
    : "no feed";

  panel.appendChild(
    el("div", { class: "shams-panel-head" }, [
      el("span", { class: "shams-title", text: "Shams projection" }),
      modeSelect,
      refresh,
      el("span", { class: "shams-spacer" }),
      statusBadge(state.status.state, state.status.detail),
      el("span", { class: "shams-badge", text: feedAge }),
    ]),
  );

  if (state.projection) {
    const { categories, teams, points } = state.projection;
    const visible = categories.filter((category) => !category.isDisplayOnly);

    const table = el("table", { class: "shams-table" });
    table.appendChild(
      el("thead", {}, [
        el("tr", {}, [
          el("th", { class: "shams-name", text: "Projected" }),
          ...visible.map((category) => el("th", { text: category.displayName })),
          el("th", { text: "Cats" }),
        ]),
      ]),
    );
    table.appendChild(
      el("tbody", {}, [
        totalsRow(teams[0], teams[1].combined, categories, points[0]),
        totalsRow(teams[1], teams[0].combined, categories, points[1]),
      ]),
    );
    panel.appendChild(table);

    panel.appendChild(
      el("div", { class: "shams-columns" }, [
        playerList(teams[0], categories, teams[0].name),
        playerList(teams[1], categories, teams[1].name),
      ]),
    );

    if (state.adds) {
      panel.appendChild(el("div", { class: "shams-columns" }, [el("div", { class: "shams-column" }, [addsList(state.adds)])]));
    }

    panel.appendChild(
      el("div", {
        class: "shams-sub",
        text: `${state.projection.weekStart} → ${state.projection.weekEnd} · each cell shows the projected total, with banked + remaining beneath it.`,
      }),
    );
  } else {
    panel.appendChild(el("div", { class: "shams-empty", text: state.status.detail }));
  }

  anchor.parentElement?.insertBefore(panel, anchor.nextSibling);
}
