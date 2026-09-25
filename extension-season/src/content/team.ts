// Team / roster pages: inject the games-remaining column.

import { loadMatchup, loadPageContext, resolveTeamKey, todayIso } from "./context";
import { findRosterTable, renderGamesColumn } from "../overlay/rosterColumn";
import { whenPresent } from "../overlay/dom";

async function run(): Promise<void> {
  const table = await whenPresent(() => findRosterTable());
  if (!table) return; // not a roster page

  const context = await loadPageContext();
  const teamKey = resolveTeamKey(context);
  if (!teamKey) return;

  const today = todayIso();
  let weekStart = today;
  let weekEnd = today;
  try {
    const matchup = await loadMatchup(teamKey);
    weekStart = matchup.weekStart || today;
    weekEnd = matchup.weekEnd || today;
  } catch {
    // Preseason or a league without matchups: fall back to the current Mon–Sun window.
    const date = new Date(`${today}T00:00:00Z`);
    const monday = new Date(date);
    monday.setUTCDate(date.getUTCDate() - ((date.getUTCDay() + 6) % 7));
    const sunday = new Date(monday);
    sunday.setUTCDate(monday.getUTCDate() + 6);
    weekStart = monday.toISOString().slice(0, 10);
    weekEnd = sunday.toISOString().slice(0, 10);
  }

  renderGamesColumn({ feed: context.feed, weekStart, weekEnd, today });
}

run().catch((error: unknown) => {
  // Fail loudly in the console rather than silently rendering nothing — the same
  // instinct as the draft assistant's emitStatus.
  console.warn("[shams] roster overlay failed:", error);
});
