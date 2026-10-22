// The trade insights panel on Yahoo's Trade Hub page: a team profile (strengths, neutral,
// weaknesses and needs, by category) for any team, and a league grid ranking every team in
// every category or slot.

import type { Feed } from "../feed/types";
import type { CategoryStanding, Grade, LeagueProfile, ProfileMode, ProfiledPlayer, TeamProfile } from "../engine/teamProfile";
import { MODE_LABELS, PRIOR_GAMES } from "../engine/statWindows";
import { SHAMS_ATTR, clearInjected, el, formatStat, statusBadge, toggle } from "./dom";

const MARKER = "trade-hub-panel";

export type TradeHubView = "profile" | "grid";
export type GridBasis = "categories" | "slots";

export const PROFILE_MODES: ProfileMode[] = ["ros", "season", "last30d", "last7d"];

const PROFILE_MODE_LABELS: Record<ProfileMode, string> = { ...MODE_LABELS, ros: "Rest of season" };

export interface TradeHubState {
  mode: ProfileMode;
  view: TradeHubView;
  basis: GridBasis;
  selectedTeamKey: string | null;
  userTeamKey: string | null;
  today: string;
  tradeEndDate: string;
  feed: Feed | null;
  profile: LeagueProfile | null;
  status: { state: "loading" | "ready" | "error"; detail: string };
}

export interface TradeHubCallbacks {
  onModeChange: (mode: ProfileMode) => void;
  onViewChange: (view: TradeHubView) => void;
  onBasisChange: (basis: GridBasis) => void;
  onTeamChange: (teamKey: string) => void;
  onRefresh: () => void;
}

/** Yahoo's React mount point. The panel goes before it, never inside, so React never owns it. */
export function findTradeHubRoot(): HTMLElement | null {
  return document.getElementById("trade_hub");
}

export function ordinal(rank: number): string {
  const tens = rank % 100;
  if (tens >= 11 && tens <= 13) return `${rank}th`;
  return `${rank}${{ 1: "st", 2: "nd", 3: "rd" }[rank % 10] ?? "th"}`;
}

const GRADE_LABELS: Record<Grade, string> = { strong: "Strengths", neutral: "Neutral", weak: "Weaknesses" };

function zClass(z: number): string {
  if (z >= 1) return "shams-z-pos2";
  if (z >= 0.35) return "shams-z-pos1";
  if (z <= -1) return "shams-z-neg2";
  if (z <= -0.35) return "shams-z-neg1";
  return "";
}

function weeklyText(row: CategoryStanding): string {
  const isPercentage = row.displayName.includes("%");
  return isPercentage ? formatStat(row.weekly, true) : `${formatStat(row.weekly, false)}/wk`;
}

function gradeColumn(team: TeamProfile, grade: Grade): HTMLElement {
  const rows = team.categories.filter((row) => row.grade === grade).sort((a, b) => a.rank - b.rank);
  const body = rows.length
    ? el(
        "table",
        { class: "shams-table" },
        [
          el(
            "tbody",
            {},
            rows.map((row) =>
              el("tr", {}, [
                el("td", { class: `shams-name shams-grade-${grade}`, text: row.displayName }),
                el("td", { text: ordinal(row.rank), title: `beats ${Math.round(row.winShare * 100)}% of the league` }),
                el("td", { class: "shams-split", text: weeklyText(row) }),
              ]),
            ),
          ),
        ],
      )
    : el("div", { class: "shams-empty", text: "—" });

  return el("div", { class: "shams-column shams-grade-column" }, [el("h4", { text: GRADE_LABELS[grade] }), body]);
}

function sourceTag(player: ProfiledPlayer): HTMLElement | null {
  const tags: Partial<Record<ProfiledPlayer["source"], [string, string]>> = {
    projection: [" (proj)", "No current-season games yet: the preseason projection"],
    previous: [" (last yr)", "No projection and no games yet: last season's averages"],
    none: [" (no stats)", "Not matched to NBA stats, so left out of every lineup"],
  };
  const tag = tags[player.source];
  return tag ? el("span", { class: "shams-source", text: tag[0], title: tag[1] }) : null;
}

function rosterTable(team: TeamProfile, profile: LeagueProfile): HTMLElement {
  const table = el("table", { class: "shams-table" });
  table.appendChild(
    el("thead", {}, [
      el("tr", {}, [
        el("th", { class: "shams-name", text: "Player" }),
        el("th", { text: "Pos" }),
        el("th", { text: "Games", title: "NBA games left in the horizon" }),
        el("th", { text: "Starts", title: "Games he starts when the best lineup is set every day" }),
        el("th", { text: "Value", title: "Per-game value: summed category z-scores against every rostered player" }),
        ...profile.categories.map((category) => el("th", { text: category.displayName })),
      ]),
    ]),
  );

  const body = el("tbody");
  for (const player of team.players) {
    const row = el("tr", { class: player.injured ? "shams-injured" : "" }, [
      el("td", { class: "shams-name" }, [
        el("span", { text: player.name }),
        el("span", { class: "shams-source", text: ` ${player.teamAbbr}` }),
        player.injured ? el("span", { class: "shams-chip shams-chip-il", text: player.selectedPosition }) : null,
        sourceTag(player),
      ]),
      el("td", { text: player.eligiblePositions.filter((p) => !["G", "F", "Util", "IL", "IL+"].includes(p)).join(",") }),
      el("td", { text: String(player.gamesLeft) }),
      el("td", { text: player.injured || player.source === "none" ? "–" : String(player.starts) }),
      el("td", { class: zClass(player.value / 3), text: player.source === "none" ? "–" : player.value.toFixed(1) }),
      ...profile.categories.map((category) => {
        const z = player.z[category.statId];
        return z === undefined
          ? el("td", { text: "–" })
          : el("td", { class: zClass(z), text: z.toFixed(1) });
      }),
    ]);
    body.appendChild(row);
  }
  table.appendChild(body);
  return el("div", { class: "shams-scroll" }, [table]);
}

function profileView(state: TradeHubState, profile: LeagueProfile, callbacks: TradeHubCallbacks): HTMLElement[] {
  const team =
    profile.teams.find((entry) => entry.teamKey === state.selectedTeamKey) ??
    profile.teams.find((entry) => entry.teamKey === state.userTeamKey) ??
    profile.teams[0];
  if (!team) return [el("div", { class: "shams-empty", text: "No teams in this league." })];

  const select = el("select", { class: "shams-select-light" }) as HTMLSelectElement;
  for (const entry of profile.teams) {
    const option = el("option", {
      text: `${entry.name}${entry.manager ? ` (${entry.manager})` : ""}${entry.teamKey === state.userTeamKey ? " — you" : ""}`,
    }) as HTMLOptionElement;
    option.value = entry.teamKey;
    option.selected = entry.teamKey === team.teamKey;
    select.appendChild(option);
  }
  select.addEventListener("change", () => callbacks.onTeamChange(select.value));

  const categoryCount = profile.categories.length;
  const summary = el("div", { class: "shams-summary" }, [
    select,
    el("span", {
      text: `${ordinal(team.rank)} of ${profile.teams.length}`,
      class: "shams-chip shams-chip-strong",
      title: "League rank by expected categories won",
    }),
    el("span", {
      text: `${team.expectedWins.toFixed(1)} of ${categoryCount} categories won against a typical league opponent`,
    }),
    el("span", { class: "shams-spacer" }),
    el("span", { class: "shams-label", text: "Needs" }),
    ...(team.needs.length
      ? team.needs.map((need) => el("span", { class: `shams-chip shams-grade-${need.grade}`, text: need.displayName }))
      : [el("span", { class: "shams-split", text: "none" })]),
  ]);

  const notes: string[] = [];
  const injured = team.players.filter((player) => player.injured).length;
  if (injured) notes.push(`${injured} on IL, left out of every lineup`);
  if (team.unmatched) notes.push(`${team.unmatched} not matched to NBA stats`);

  return [
    summary,
    el("div", { class: "shams-columns" }, [
      gradeColumn(team, "strong"),
      gradeColumn(team, "neutral"),
      gradeColumn(team, "weak"),
    ]),
    notes.length ? el("div", { class: "shams-sub", text: notes.join(" · ") }) : null,
    rosterTable(team, profile),
  ].filter((node): node is HTMLElement => node !== null);
}

function gridView(state: TradeHubState, profile: LeagueProfile, callbacks: TradeHubCallbacks): HTMLElement[] {
  const bySlots = state.basis === "slots";
  const columns = bySlots ? profile.slotTypes : profile.categories.map((category) => category.displayName);

  const table = el("table", { class: "shams-table" });
  table.appendChild(
    el("thead", {}, [
      el("tr", {}, [
        el("th", { text: "#" }),
        el("th", { class: "shams-name", text: "Team" }),
        ...columns.map((column) => el("th", { text: column })),
        el("th", { text: "Cats", title: "Expected categories won against a typical league opponent" }),
      ]),
    ]),
  );

  const body = el("tbody");
  for (const team of profile.teams) {
    const cells = bySlots
      ? team.slots.map((row) =>
          el("td", {
            class: `shams-grade-${row.grade}`,
            text: ordinal(row.rank),
            title: `${row.slot}: ${row.value.toFixed(1)} value above replacement per week`,
          }),
        )
      : team.categories.map((row) =>
          el("td", {
            class: `shams-grade-${row.grade}`,
            text: ordinal(row.rank),
            title: `${row.displayName}: ${weeklyText(row)}, beats ${Math.round(row.winShare * 100)}% of the league`,
          }),
        );

    const row = el(
      "tr",
      { class: team.teamKey === state.userTeamKey ? "shams-clickable shams-mine" : "shams-clickable", title: "Open this team's profile" },
      [
        el("td", { text: String(team.rank) }),
        el("td", { class: "shams-name", text: team.name }),
        ...cells,
        el("td", { class: "shams-score", text: team.expectedWins.toFixed(1) }),
      ],
    );
    row.addEventListener("click", () => {
      callbacks.onTeamChange(team.teamKey);
      callbacks.onViewChange("profile");
    });
    body.appendChild(row);
  }
  table.appendChild(body);

  return [
    el("div", { class: "shams-summary" }, [
      toggle<GridBasis>([["categories", "Categories"], ["slots", "Roster slots"]], state.basis, callbacks.onBasisChange),
      el("span", {
        class: "shams-split",
        text: bySlots
          ? "Slot ranks: value each slot's starters produce, the way Yahoo grades positions."
          : "Category ranks on expected weekly totals. Click a team for its profile.",
      }),
    ]),
    el("div", { class: "shams-scroll" }, [table]),
  ];
}

function footnote(state: TradeHubState, profile: LeagueProfile): string {
  const { start, end, weeks } = profile.horizon;
  const lines =
    state.mode === "ros"
      ? `Player lines blend the preseason projection with this season so far (the projection counts as ${PRIOR_GAMES} games).`
      : `Player lines use ${PROFILE_MODE_LABELS[state.mode].toLowerCase()}.`;
  return (
    `${start} → ${end} (${weeks.toFixed(1)} weeks): every roster plays out the real schedule with its best ` +
    `lineup each day; IL slots sit out. ${lines} Strong and weak are the top and bottom thirds of the league.`
  );
}

export function renderTradeHubPanel(state: TradeHubState, callbacks: TradeHubCallbacks): void {
  const anchor = findTradeHubRoot();
  if (!anchor) return;

  clearInjected(MARKER);

  const panel = el("div", { class: "shams-panel" });
  panel.setAttribute(SHAMS_ATTR, MARKER);

  const modeSelect = el("select", { class: "shams-select" }) as HTMLSelectElement;
  for (const mode of PROFILE_MODES) {
    const option = el("option", { text: PROFILE_MODE_LABELS[mode] }) as HTMLOptionElement;
    option.value = mode;
    option.selected = mode === state.mode;
    modeSelect.appendChild(option);
  }
  modeSelect.addEventListener("change", () => callbacks.onModeChange(modeSelect.value as ProfileMode));

  const refresh = el("button", { class: "shams-button", text: "Refresh" });
  refresh.addEventListener("click", () => callbacks.onRefresh());

  const feedAge = state.feed
    ? `feed ${state.feed.meta.season} · ${new Date(state.feed.meta.generated_at).toLocaleDateString()}`
    : "no feed";
  const pastDeadline = state.tradeEndDate && state.today > state.tradeEndDate;

  panel.appendChild(
    el("div", { class: "shams-panel-head" }, [
      el("span", { class: "shams-title", text: "Shams trade insights" }),
      toggle<TradeHubView>([["profile", "Team profile"], ["grid", "League grid"]], state.view, callbacks.onViewChange),
      modeSelect,
      refresh,
      el("span", { class: "shams-spacer" }),
      pastDeadline ? el("span", { class: "shams-badge shams-badge-error", text: `trade deadline was ${state.tradeEndDate}` }) : null,
      statusBadge(state.status.state, state.status.detail),
      el("span", { class: "shams-badge", text: feedAge }),
    ]),
  );

  const profile = state.profile;
  if (profile && profile.horizon.days > 0) {
    const view = state.view === "grid" ? gridView(state, profile, callbacks) : profileView(state, profile, callbacks);
    for (const node of view) panel.appendChild(node);
    panel.appendChild(el("div", { class: "shams-sub", text: footnote(state, profile) }));
  } else if (profile) {
    panel.appendChild(el("div", { class: "shams-empty", text: "No games left this season." }));
  } else {
    panel.appendChild(el("div", { class: "shams-empty", text: state.status.detail }));
  }

  anchor.parentElement?.insertBefore(panel, anchor);
}
