// Games-remaining column, injected into Yahoo's own roster table (#statTable0).
//
// Pure schedule math, so it renders without any projection work — the cheapest useful
// thing the extension does, and the one worth showing first.

import type { Feed } from "../feed/types";
import { gameDatesFor, weekGames } from "../engine/schedule";
import { SHAMS_ATTR, clearInjected, el, gamesClass } from "./dom";
import { resolveNbaId } from "../engine/playerIdentity";

const MARKER = "games-column";

interface Options {
  feed: Feed;
  weekStart: string;
  weekEnd: string;
  today: string;
}

/** Yahoo's roster table, ignoring anything an extension (ours or another) injected. */
export function findRosterTable(): HTMLTableElement | null {
  const table = document.getElementById("statTable0");
  return table instanceof HTMLTableElement ? table : null;
}

function teamAbbrFromRow(row: HTMLTableRowElement): string {
  // The player cell reads like "Jaime Jaquez Jr.Player Note MIL - SG,SF,PF".
  const cell = row.querySelector("td.player");
  const text = cell?.textContent ?? "";
  const match = /\b([A-Z]{2,3})\s+-\s+[A-Z]/.exec(text);
  return match?.[1] ?? "";
}

export function renderGamesColumn(options: Options): number {
  const table = findRosterTable();
  if (!table) return 0;

  clearInjected(MARKER);

  const headerRows = Array.from(table.querySelectorAll("thead tr"));
  const labelRow = headerRows[headerRows.length - 1];
  const groupRow = headerRows.length > 1 ? headerRows[0] : null;

  // Insert directly after the player name column so the number sits beside the player.
  const insertAt = (row: HTMLTableRowElement): number => {
    const cells = Array.from(row.children);
    const playerIndex = cells.findIndex((cell) => cell.classList.contains("player"));
    return playerIndex >= 0 ? playerIndex + 1 : 1;
  };

  if (labelRow) {
    const header = el("th", { class: "shams-col", text: "SHAMS", title: "Games remaining this week / total" });
    header.setAttribute(SHAMS_ATTR, MARKER);
    const cells = Array.from(labelRow.children);
    const playerIndex = cells.findIndex((cell) => (cell.textContent ?? "").trim() === "Players");
    labelRow.insertBefore(header, cells[playerIndex >= 0 ? playerIndex + 1 : 1] ?? null);
  }
  if (groupRow) {
    const spacer = el("th", { text: "" });
    spacer.setAttribute(SHAMS_ATTR, MARKER);
    groupRow.insertBefore(spacer, groupRow.children[1] ?? null);
  }

  let rendered = 0;
  for (const row of Array.from(table.querySelectorAll<HTMLTableRowElement>("tbody tr"))) {
    const playerId = row.querySelector<HTMLElement>("[data-ys-playerid]")?.dataset["ysPlayerid"];
    const playerName = (row.querySelector("td.player a")?.textContent ?? "").trim();
    const abbr = teamAbbrFromRow(row);
    const cell = el("td", { class: "Ta-c" });
    cell.setAttribute(SHAMS_ATTR, MARKER);

    if (playerId && abbr) {
      const nbaId = resolveNbaId(options.feed.index, playerId, playerName);
      const played = new Set(
        (nbaId ? options.feed.players.players[nbaId]?.games ?? [] : [])
          .filter((game) => game[0] >= options.weekStart && game[0] <= options.today)
          .map((game) => game[0]),
      );
      const games = weekGames(options.feed.schedule, abbr, options.weekStart, options.weekEnd, options.today, played);
      const dates = gameDatesFor(options.feed.schedule, abbr, options.weekStart, options.weekEnd);

      cell.appendChild(
        el("span", {
          class: gamesClass(games.remaining),
          text: `${games.remaining}/${games.total}`,
          title: dates.length ? `Games this week: ${dates.join(", ")}` : "No games this week",
        }),
      );
      rendered += 1;
    } else {
      cell.textContent = "";
    }

    row.insertBefore(cell, row.children[insertAt(row)] ?? null);
  }

  return rendered;
}
