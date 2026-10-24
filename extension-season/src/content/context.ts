// Shared page bootstrap for both content scripts: work out which league, team and week
// the page is showing, and fetch the rosters the projection needs.

import { getFeed } from "../feed/client";
import type { Feed } from "../feed/types";
import {
  fetchGameKey,
  fetchLeagueSettings,
  fetchMatchup,
  fetchRoster,
  fetchUserTeams,
  parsePageContext,
} from "../yahoo/client";
import type { LeagueSettings, Matchup, YahooPlayer } from "../yahoo/types";
import { datesInRange } from "../engine/schedule";

/** Today's date in US Eastern time, the zone of NBA game dates, the feed's schedule and
 *  Yahoo's fantasy day. The browser's own date runs a day ahead in Asia, which would
 *  count tonight's games as already played. Prefer Yahoo's `current_date` when there is
 *  a league to ask (`PageContext.today`). */
export function todayIso(now: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/New_York",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(now);
}

export interface PageContext {
  feed: Feed;
  gameKey: string;
  leagueKey: string;
  settings: LeagueSettings;
  userTeamKey: string | null;
  /** Yahoo's fantasy day for this league, or the US Eastern date if Yahoo omits it. */
  today: string;
}

export async function loadPageContext(force = false): Promise<PageContext> {
  const { leagueId } = parsePageContext(location.pathname);
  if (!leagueId) throw new Error("no league id in the page URL");

  const [feed, gameKey] = await Promise.all([getFeed(force), fetchGameKey()]);
  const leagueKey = `${gameKey}.l.${leagueId}`;
  const [settings, userTeams] = await Promise.all([
    fetchLeagueSettings(leagueKey),
    fetchUserTeams(gameKey).catch(() => []),
  ]);

  const userTeamKey = userTeams.find((team) => team.teamKey.startsWith(`${leagueKey}.`))?.teamKey ?? null;

  return { feed, gameKey, leagueKey, settings, userTeamKey, today: settings.currentDate || todayIso() };
}

export function teamKeyFor(leagueKey: string, teamId: string): string {
  return `${leagueKey}.t.${teamId}`;
}

/** Which team's page is this — the URL's team, the matchup's `mid1`, or the user's own. */
export function resolveTeamKey(context: PageContext): string | null {
  const { teamId } = parsePageContext(location.pathname);
  if (teamId) return teamKeyFor(context.leagueKey, teamId);

  const mid1 = new URLSearchParams(location.search).get("mid1");
  if (mid1 && /^\d+$/.test(mid1)) return teamKeyFor(context.leagueKey, mid1);

  return context.userTeamKey;
}

export async function loadMatchup(teamKey: string, week?: number): Promise<Matchup> {
  return fetchMatchup(teamKey, week);
}

async function mapWithConcurrency<T, R>(
  items: T[],
  limit: number,
  worker: (item: T) => Promise<R>,
): Promise<R[]> {
  const results: R[] = [];
  for (let index = 0; index < items.length; index += limit) {
    const slice = items.slice(index, index + limit);
    results.push(...(await Promise.all(slice.map(worker))));
  }
  return results;
}

/** Rosters for every day of the week, plus today, each with every player's line for
 * that day.
 *
 * Each day's lineup decides who counts that day: a player benched on Tuesday is not
 * credited with Tuesday's line, and one benched in Sunday's lineup is not projected for
 * Sunday. For a day still to come Yahoo returns the lineup the manager set for it, or the
 * current one carried forward. A day that fails to load is left out, so the projection
 * falls back to today's lineup instead of an empty one. */
export async function loadRosterByDate(
  teamKey: string,
  weekStart: string,
  weekEnd: string,
  today: string,
): Promise<Record<string, YahooPlayer[]>> {
  const week = weekStart <= weekEnd ? datesInRange(weekStart, weekEnd) : [];
  const dates = week.includes(today) ? week : [...week, today];

  const rosterByDate: Record<string, YahooPlayer[]> = {};
  await mapWithConcurrency(dates, 4, async (date) => {
    try {
      rosterByDate[date] = await fetchRoster(teamKey, date);
    } catch {
      if (date <= today) rosterByDate[date] = [];
    }
  });

  return rosterByDate;
}
