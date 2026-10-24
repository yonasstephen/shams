// The matchup projection, ported from tools/matchup/matchup_projection.py.
//
// Two rules carried over verbatim from CLAUDE.md, because getting either wrong
// double-counts a game:
//   * banked stats and projected stats stay in separate buckets to the very end;
//   * today counts as banked if a box score exists for it, otherwise as remaining.
//
// Banked stats come from Yahoo first: its line for each day includes games in progress,
// while the feed's box scores stop at its nightly build. The feed is the fallback for a
// day Yahoo sent no line for.

import type { Feed, StatLine } from "../feed/types";
import type { StatCategory, YahooPlayer } from "../yahoo/types";
import { fieldForStatName, isPercentageStat } from "./statMap";
import { gamesInRange, playerAverages, sumRows, type ProjectionMode, type StatSource } from "./statWindows";
import { isActivePosition, optimizeRosterPositions } from "./rosterOptimizer";
import { datesInRange, gameDatesFor, weekGames } from "./schedule";
import { resolveNbaId } from "./playerIdentity";

export interface Totals extends Record<string, number> {}

export interface PlayerContribution {
  playerKey: string;
  playerId: string;
  name: string;
  nbaId: string | null;
  teamAbbr: string;
  selectedPosition: string;
  status: string;
  /** Games on his NBA team's schedule this week. */
  totalGames: number;
  /** Games still to come while he is on this roster, whatever slot he is in. */
  remainingGames: number;
  /** The remaining games the projection counts: those on days he is in an active slot. */
  projectedGames: number;
  /** Dates of remaining games he sits on the bench for, which the projection leaves out. */
  benchedDates: string[];
  /** First day on this roster, when he joined after the week began. */
  addedOn?: string;
  /** First day off this roster, when he leaves before the week ends. */
  droppedOn?: string;
  playedGames: number;
  current: Totals;
  projected: Totals;
  source: StatSource;
  isActiveToday: boolean;
}

export interface TeamProjection {
  teamKey: string;
  name: string;
  current: Totals;
  remaining: Totals;
  combined: Totals;
  players: PlayerContribution[];
}

export interface TeamPoints {
  win: number;
  loss: number;
  tie: number;
  total: number;
}

export interface TeamInput {
  teamKey: string;
  name: string;
  /** Roster on each date of the week as Yahoo has it: the lineup that played on past
   *  days, and the lineup set for each day still to come. A player's `stats` on a date is
   *  Yahoo's line for that day. A day still to come that is missing or empty falls back
   *  to today's lineup. */
  rosterByDate: Record<string, YahooPlayer[]>;
  /** Yahoo's own totals for the week so far. When present they are the team's banked
   *  line, so the projection starts from the numbers on the scoreboard above it. */
  weekTotals?: Totals;
  optimize: boolean;
  playerRanks?: Record<string, number>;
}

export interface ProjectionInput {
  feed: Feed;
  categories: StatCategory[];
  rosterPositions: string[];
  weekStart: string;
  weekEnd: string;
  today: string;
  mode: ProjectionMode;
  teams: [TeamInput, TeamInput];
  /** Player keys the user has excluded from the projection. */
  excluded?: Set<string>;
}

export interface ProjectionResult {
  categories: StatCategory[];
  weekStart: string;
  weekEnd: string;
  teams: [TeamProjection, TeamProjection];
  points: [TeamPoints, TeamPoints];
}

const SHOOTING_KEYS = ["_FGM", "_FGA", "_FTM", "_FTA"] as const;

// Yahoo injury statuses that mean he will not play, matching the web app's waiver page.
const OUT_STATUSES = new Set(["INJ", "O", "OUT", "IR", "SUSP", "PUP", "NA"]);

/** Benching a player who is out anyway is not an oversight worth flagging. */
export function isOutStatus(status: string): boolean {
  return OUT_STATUSES.has(status.toUpperCase());
}

function emptyTotals(categories: StatCategory[]): Totals {
  const totals: Totals = {};
  for (const category of categories) {
    if (category.isDisplayOnly) continue;
    totals[category.statId] = 0;
  }
  for (const key of SHOOTING_KEYS) totals[key] = 0;
  return totals;
}

/** One player's line for `games` games: counting stats scale, percentages do not. */
export function lineToStats(line: StatLine, categories: StatCategory[], games: number): Totals {
  const stats: Totals = {};
  for (const category of categories) {
    if (category.isDisplayOnly) continue;
    const field = fieldForStatName(category.displayName) ?? fieldForStatName(category.name);
    if (!field) {
      stats[category.statId] = 0;
      continue;
    }
    const value = line[field] ?? 0;
    stats[category.statId] = isPercentageStat(category.displayName) ? value : value * games;
  }
  stats["_FGM"] = (line.fgm ?? 0) * games;
  stats["_FGA"] = (line.fga ?? 0) * games;
  stats["_FTM"] = (line.ftm ?? 0) * games;
  stats["_FTA"] = (line.fta ?? 0) * games;
  return stats;
}

/** Sum player lines into a team total, recomputing percentages from pooled volume —
 *  a team's FG% is made shots over attempts, never an average of averages. */
export function sumContributions(lines: Totals[], categories: StatCategory[]): Totals {
  const totals = emptyTotals(categories);

  for (const line of lines) {
    for (const key of SHOOTING_KEYS) totals[key] = (totals[key] ?? 0) + (line[key] ?? 0);
    for (const category of categories) {
      if (category.isDisplayOnly || isPercentageStat(category.displayName)) continue;
      totals[category.statId] = (totals[category.statId] ?? 0) + (line[category.statId] ?? 0);
    }
  }

  applyPercentages(totals, categories);
  return totals;
}

/** Rebuild FG% and FT% from pooled makes and attempts, in place. */
export function applyPercentages(totals: Totals, categories: StatCategory[]): void {
  for (const category of categories) {
    if (category.isDisplayOnly) continue;
    if (category.displayName === "FG%") {
      totals[category.statId] = (totals["_FGA"] ?? 0) > 0 ? (totals["_FGM"] ?? 0) / (totals["_FGA"] as number) : 0;
    } else if (category.displayName === "FT%") {
      totals[category.statId] = (totals["_FTA"] ?? 0) > 0 ? (totals["_FTM"] ?? 0) / (totals["_FTA"] as number) : 0;
    }
  }
}

function combineTotals(current: Totals, remaining: Totals, categories: StatCategory[]): Totals {
  const totals = emptyTotals(categories);

  for (const category of categories) {
    if (category.isDisplayOnly || isPercentageStat(category.displayName)) continue;
    totals[category.statId] = (current[category.statId] ?? 0) + (remaining[category.statId] ?? 0);
  }
  for (const key of SHOOTING_KEYS) {
    totals[key] = (current[key] ?? 0) + (remaining[key] ?? 0);
  }

  applyPercentages(totals, categories);
  return totals;
}

/** Category W-L-T. Ties on FG%/FT% break on volume, matching the Python. */
export function calculateProjectedPoints(
  categories: StatCategory[],
  teamA: Totals,
  teamB: Totals,
): [TeamPoints, TeamPoints] {
  const a: TeamPoints = { win: 0, loss: 0, tie: 0, total: 0 };
  const b: TeamPoints = { win: 0, loss: 0, tie: 0, total: 0 };

  const awardTo = (winner: TeamPoints, loser: TeamPoints) => {
    winner.win += 1;
    loser.loss += 1;
  };

  for (const category of categories) {
    if (category.isDisplayOnly) continue;

    const aValue = teamA[category.statId] ?? 0;
    const bValue = teamB[category.statId] ?? 0;
    const lowerIsBetter = category.sortOrder === "0";

    if (Math.abs(aValue - bValue) < 0.001) {
      const volumeKey =
        category.displayName === "FG%" ? "_FGA" : category.displayName === "FT%" ? "_FTA" : null;

      if (volumeKey) {
        const aVolume = teamA[volumeKey] ?? 0;
        const bVolume = teamB[volumeKey] ?? 0;
        if (Math.abs(aVolume - bVolume) > 0.001) {
          if (aVolume > bVolume) awardTo(a, b);
          else awardTo(b, a);
          continue;
        }
      }
      a.tie += 1;
      b.tie += 1;
      continue;
    }

    if ((aValue > bValue && !lowerIsBetter) || (aValue < bValue && lowerIsBetter)) awardTo(a, b);
    else awardTo(b, a);
  }

  a.total = a.win;
  b.total = b.win;
  return [a, b];
}

function projectTeam(input: ProjectionInput, team: TeamInput): TeamProjection {
  const { feed, categories, weekStart, weekEnd, today, mode } = input;
  const excluded = input.excluded ?? new Set<string>();

  const pastDates = Object.keys(team.rosterByDate)
    .filter((date) => date >= weekStart && date <= today && date <= weekEnd)
    .sort();
  const todayRoster = team.rosterByDate[today] ?? team.rosterByDate[pastDates[pastDates.length - 1] ?? ""] ?? [];
  const futureDates = Object.keys(team.rosterByDate)
    .filter((date) => date > today && date >= weekStart && date <= weekEnd)
    .sort();

  /** The lineup for a day still to come, or today's when Yahoo sent none for it. */
  const rosterOn = (date: string): YahooPlayer[] => {
    const roster = team.rosterByDate[date];
    return date > today && !roster?.length ? todayRoster : roster ?? [];
  };

  // Each day's slot for everyone on the roster that day. A player benched on Tuesday is
  // not credited with Tuesday's line, and one benched in Sunday's lineup is not projected
  // for Sunday.
  const lineups = new Map<string, Map<string, string>>();
  const lineupOn = (date: string): Map<string, string> => {
    let lineup = lineups.get(date);
    if (!lineup) {
      lineup = new Map(rosterOn(date).map((player) => [player.playerKey, player.selectedPosition]));
      lineups.set(date, lineup);
    }
    return lineup;
  };
  const isActiveOn = (date: string, playerKey: string): boolean => {
    const position = lineupOn(date).get(playerKey);
    return position !== undefined && isActivePosition(position);
  };

  // Days whose roster Yahoo sent, which are the only ones that can say when a player
  // joined or left. A day it failed to send would otherwise read as everyone gone.
  const knownDates = datesInRange(weekStart, weekEnd).filter((date) => rosterOn(date).length > 0);

  // Today's active slots, or with `optimize`, the optimizer's for the rest of the week.
  let futureActive: Set<string>;
  if (team.optimize) {
    const withGames = new Set(
      todayRoster
        .filter((player) => gameDatesFor(feed.schedule, player.teamAbbr, today, weekEnd).length > 0)
        .map((player) => player.playerKey),
    );
    const assignments = optimizeRosterPositions(
      todayRoster.map((player) => ({ playerKey: player.playerKey, eligiblePositions: player.eligiblePositions })),
      input.rosterPositions,
      withGames,
      team.playerRanks ?? {},
    );
    futureActive = new Set(
      Object.entries(assignments).filter(([, position]) => isActivePosition(position)).map(([key]) => key),
    );
  } else {
    futureActive = new Set(
      todayRoster.filter((player) => isActivePosition(player.selectedPosition)).map((player) => player.playerKey),
    );
  }

  const seen = new Set<string>();
  const contributions: PlayerContribution[] = [];
  const currentLines: Totals[] = [];
  const remainingLines: Totals[] = [];

  // Everyone on the roster at some point this week, including a player added for a day
  // still to come.
  const rosterUnion: YahooPlayer[] = [];
  for (const date of [...pastDates, today, ...futureDates]) {
    for (const player of team.rosterByDate[date] ?? []) {
      if (seen.has(player.playerKey)) continue;
      seen.add(player.playerKey);
      rosterUnion.push(player);
    }
  }
  for (const player of todayRoster) {
    if (!seen.has(player.playerKey)) {
      seen.add(player.playerKey);
      rosterUnion.push(player);
    }
  }

  // Yahoo's line for each player on each day, whatever slot they were in.
  const yahooLines = new Map<string, Map<string, Totals>>();
  for (const date of new Set([...pastDates, today])) {
    const lines = new Map<string, Totals>();
    for (const player of team.rosterByDate[date] ?? []) {
      if (player.stats) lines.set(player.playerKey, player.stats);
    }
    yahooLines.set(date, lines);
  }

  for (const player of rosterUnion) {
    const nbaId = resolveNbaId(feed.index, player.playerId, player.name);
    const entry = nbaId ? feed.players.players[nbaId] : undefined;

    // Banked: on each day this player started, Yahoo's line, or the feed's box score
    // when Yahoo sent none.
    const bankedDays: Totals[] = [];
    const playedDates = new Set<string>();
    for (const date of pastDates) {
      if (!isActiveOn(date, player.playerKey)) continue;
      const yahooLine = yahooLines.get(date)?.get(player.playerKey);
      const lines = yahooLine
        ? [yahooLine]
        : gamesInRange(entry, date, date).map((row) => lineToStats(sumRows([row]), categories, 1));
      if (lines.length) playedDates.add(date);
      bankedDays.push(...lines);
    }
    const current = excluded.has(player.playerKey)
      ? emptyTotals(categories)
      : sumContributions(bankedDays, categories);

    // Remaining: scheduled games left while he is on the roster. The projection counts
    // those on days he is in an active slot, times his window averages. A game Yahoo
    // already has a line for today has tipped off, even if he sat on the bench.
    const allPlayed = new Set(
      (entry?.games ?? []).filter((row) => row[0] >= weekStart && row[0] <= today).map((row) => row[0]),
    );
    if (yahooLines.get(today)?.has(player.playerKey)) allPlayed.add(today);
    const games = weekGames(feed.schedule, player.teamAbbr, weekStart, weekEnd, today, allPlayed);
    const averages = playerAverages({
      nbaId,
      mode,
      today,
      players: feed.players,
      playersPrev: feed.playersPrev,
      projections: feed.projections.players,
    });

    const remainingDates = games.remainingDates.filter((date) => lineupOn(date).has(player.playerKey));
    let projectedGames: number;
    let benchedDates: string[] = [];
    if (excluded.has(player.playerKey)) {
      projectedGames = 0;
    } else if (team.optimize) {
      projectedGames = futureActive.has(player.playerKey) ? remainingDates.length : 0;
    } else {
      projectedGames = remainingDates.filter((date) => isActiveOn(date, player.playerKey)).length;
      benchedDates = remainingDates.filter((date) => lineupOn(date).get(player.playerKey) === "BN");
    }
    const projected = lineToStats(averages.stats, categories, projectedGames);
    if (projectedGames === 0) applyPercentages(projected, categories);

    const onRoster = knownDates.filter((date) => lineupOn(date).has(player.playerKey));
    const first = onRoster[0];
    const last = onRoster[onRoster.length - 1];

    contributions.push({
      playerKey: player.playerKey,
      playerId: player.playerId,
      name: player.name,
      nbaId,
      teamAbbr: player.teamAbbr,
      selectedPosition: player.selectedPosition,
      status: player.status,
      totalGames: games.total,
      remainingGames: remainingDates.length,
      projectedGames,
      benchedDates,
      addedOn: first && first > knownDates[0]! ? first : undefined,
      droppedOn: last && last < knownDates[knownDates.length - 1]! ? knownDates.find((date) => date > last) : undefined,
      playedGames: playedDates.size,
      current,
      projected,
      source: averages.source,
      isActiveToday: futureActive.has(player.playerKey),
    });

    currentLines.push(current);
    remainingLines.push(projected);
  }

  const current = team.weekTotals
    ? { ...emptyTotals(categories), ...team.weekTotals }
    : sumContributions(currentLines, categories);
  const remaining = sumContributions(remainingLines, categories);

  return {
    teamKey: team.teamKey,
    name: team.name,
    current,
    remaining,
    combined: combineTotals(current, remaining, categories),
    players: contributions,
  };
}

export function projectMatchup(input: ProjectionInput): ProjectionResult {
  const teamA = projectTeam(input, input.teams[0]);
  const teamB = projectTeam(input, input.teams[1]);
  const points = calculateProjectedPoints(input.categories, teamA.combined, teamB.combined);

  return {
    categories: input.categories,
    weekStart: input.weekStart,
    weekEnd: input.weekEnd,
    teams: [teamA, teamB],
    points,
  };
}
