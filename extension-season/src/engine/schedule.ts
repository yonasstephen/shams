// Games-remaining math: the schedule side of the overlay, and the multiplier behind
// every projection.

import type { ScheduleFile } from "../feed/types";

/** Yahoo and the NBA feed disagree on a handful of tricodes. */
const TEAM_ALIASES: Record<string, string> = {
  GS: "GSW",
  NO: "NOP",
  NY: "NYK",
  SA: "SAS",
  PHO: "PHX",
  WSH: "WAS",
  CHO: "CHA",
  BKN: "BKN",
  BRK: "BKN",
  UTAH: "UTA",
};

export function normalizeTeam(abbr: string): string {
  const upper = (abbr || "").toUpperCase();
  return TEAM_ALIASES[upper] ?? upper;
}

export function datesInRange(start: string, end: string): string[] {
  const dates: string[] = [];
  const cursor = new Date(`${start}T00:00:00Z`);
  const last = new Date(`${end}T00:00:00Z`);
  while (cursor <= last) {
    dates.push(cursor.toISOString().slice(0, 10));
    cursor.setUTCDate(cursor.getUTCDate() + 1);
  }
  return dates;
}

/** Dates in [start, end] on which `teamAbbr` plays, postponements excluded. */
export function gameDatesFor(
  schedule: ScheduleFile,
  teamAbbr: string,
  start: string,
  end: string,
): string[] {
  const team = normalizeTeam(teamAbbr);
  if (!team) return [];

  const dates: string[] = [];
  for (const date of datesInRange(start, end)) {
    const games = schedule.dates[date];
    if (!games) continue;
    const plays = games.some(
      (game) => (game[3] ?? "N") !== "P" && (normalizeTeam(game[0]) === team || normalizeTeam(game[1]) === team),
    );
    if (plays) dates.push(date);
  }
  return dates;
}

export interface WeekGames {
  total: number;
  remaining: number;
  played: number;
  remainingDates: string[];
}

/** Split a team's week into games already tipped off and games still to come.
 *
 * Today is the awkward case and is handled the way the Python engine handles it: a game
 * that already produced a box score is banked, and one that has not is still upcoming, so
 * it is counted exactly once.
 */
export function weekGames(
  schedule: ScheduleFile,
  teamAbbr: string,
  weekStart: string,
  weekEnd: string,
  today: string,
  playedDates: Set<string>,
): WeekGames {
  const all = gameDatesFor(schedule, teamAbbr, weekStart, weekEnd);
  const remainingDates = all.filter((date) => {
    if (date > today) return true;
    if (date < today) return false;
    return !playedDates.has(date);
  });

  return {
    total: all.length,
    remaining: remainingDates.length,
    played: all.length - remainingDates.length,
    remainingDates,
  };
}
