// Live check harness: runs the real engine and overlay against a real Yahoo page, with
// the feed fetched straight from the published branch instead of through the service
// worker. Not shipped — built ad hoc into the scratchpad for verification.

import type { Feed } from "../src/feed/types";
import { renderGamesColumn, findRosterTable } from "../src/overlay/rosterColumn";
import { gameDatesFor } from "../src/engine/schedule";

const BASE = "https://raw.githubusercontent.com/yonasstephen/shams/feed";

async function gz<T>(name: string): Promise<T> {
  const response = await fetch(`${BASE}/${name}`);
  const stream = response.body!.pipeThrough(new DecompressionStream("gzip"));
  return JSON.parse(await new Response(stream).text()) as T;
}

async function main(css: string, weekStart: string, weekEnd: string, today: string) {
  const style = document.createElement("style");
  style.textContent = css;
  document.head.appendChild(style);

  const [meta, projections, players, playersPrev, schedule, index] = await Promise.all([
    fetch(`${BASE}/meta.json`).then((r) => r.json()),
    gz<Feed["projections"]>("projections.json.gz"),
    gz<Feed["players"]>("players.json.gz"),
    gz<Feed["playersPrev"]>("players-prev.json.gz"),
    gz<Feed["schedule"]>("schedule.json.gz"),
    gz<Feed["index"]>("player-index.json.gz"),
  ]);

  const feed: Feed = { meta, projections, players, playersPrev, schedule, index };
  const rendered = renderGamesColumn({ feed, weekStart, weekEnd, today });

  const table = findRosterTable();
  const sample = Array.from(table?.querySelectorAll("tbody tr") ?? []).slice(0, 4).map((row) => {
    const cell = row.querySelector(".shams-games");
    const name = (row.querySelector("td.player a")?.textContent ?? "").trim();
    const abbr = /\b([A-Z]{2,3})\s+-\s+[A-Z]/.exec(row.querySelector("td.player")?.textContent ?? "")?.[1] ?? "";
    return { name, abbr, cell: cell?.textContent ?? null, dates: gameDatesFor(feed.schedule, abbr, weekStart, weekEnd) };
  });

  (window as unknown as Record<string, unknown>)["__shams"] = {
    season: meta.season,
    generated: meta.generated_at,
    mapped: Object.keys(index.yahoo_to_nba).length,
    scheduleDates: Object.keys(schedule.dates).length,
    rendered,
    sample,
  };
}

(window as unknown as Record<string, unknown>)["__shamsRun"] = main;
