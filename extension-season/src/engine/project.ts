// The matchup projection, ported from tools/matchup/matchup_projection.py.
//
// Two rules carried over verbatim from CLAUDE.md, because getting either wrong
// double-counts a game:
//   * banked stats and projected stats stay in separate buckets to the very end;
//   * today counts as banked if a box score exists for it, otherwise as remaining.

import type { Feed, StatLine } from "../feed/types";
import type { StatCategory, YahooPlayer } from "../yahoo/types";
import { fieldForStatName, isPercentageStat } from "./statMap";
import { gamesInRange, playerAverages, sumRows, type ProjectionMode, type StatSource } from "./statWindows";
import { isActivePosition, optimizeRosterPositions } from "./rosterOptimizer";
import { gameDatesFor, weekGames } from "./schedule";
import { resolveNbaId } from "./playerIdentity";

export interface Totals extends Record<string, number> {}

export interface PlayerContribution {
  playerKey: string;
  playerId: string;
  name: string;
  nbaId: string | null;
  teamAbbr: string;
  selectedPosition: string;
  totalGames: number;
  remainingGames: number;
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
  /** Roster as it stood on each date of the week so far, plus today for the rest. */
  rosterByDate: Record<string, YahooPlayer[]>;
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

function applyPercentages(totals: Totals, categories: StatCategory[]): void {
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

  // Which players started on which past day — a player benched on Tuesday must not be
  // credited with Tuesday's box score.
  const activeOnDate = new Map<string, Set<string>>();
  for (const date of pastDates) {
    const roster = team.rosterByDate[date] ?? [];
    activeOnDate.set(
      date,
      new Set(roster.filter((player) => isActivePosition(player.selectedPosition)).map((p) => p.playerKey)),
    );
  }

  // Forward-looking slots: either the manager's current lineup or the optimizer's.
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

  const rosterUnion: YahooPlayer[] = [];
  for (const date of [...pastDates, today]) {
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

  for (const player of rosterUnion) {
    const nbaId = resolveNbaId(feed.index, player.playerId, player.name);
    const entry = nbaId ? feed.players.players[nbaId] : undefined;

    // Banked: box scores on days this player actually started.
    const bankedRows = pastDates
      .filter((date) => activeOnDate.get(date)?.has(player.playerKey))
      .flatMap((date) => gamesInRange(entry, date, date));
    const playedDates = new Set(bankedRows.map((row) => row[0]));
    const bankedLine = sumRows(bankedRows);
    const current = excluded.has(player.playerKey)
      ? emptyTotals(categories)
      : lineToStats(bankedLine, categories, 1);
    if (!excluded.has(player.playerKey)) applyPercentages(current, categories);

    // Remaining: scheduled games left, times this player's window averages.
    const allPlayed = new Set(
      (entry?.games ?? []).filter((row) => row[0] >= weekStart && row[0] <= today).map((row) => row[0]),
    );
    const games = weekGames(feed.schedule, player.teamAbbr, weekStart, weekEnd, today, allPlayed);
    const isFutureActive = futureActive.has(player.playerKey) && !excluded.has(player.playerKey);
    const averages = playerAverages({
      nbaId,
      mode,
      today,
      players: feed.players,
      playersPrev: feed.playersPrev,
      projections: feed.projections.players,
    });

    const remainingGames = isFutureActive ? games.remaining : 0;
    const projected = lineToStats(averages.stats, categories, remainingGames);
    if (remainingGames === 0) applyPercentages(projected, categories);

    contributions.push({
      playerKey: player.playerKey,
      playerId: player.playerId,
      name: player.name,
      nbaId,
      teamAbbr: player.teamAbbr,
      selectedPosition: player.selectedPosition,
      totalGames: games.total,
      remainingGames,
      playedGames: playedDates.size,
      current,
      projected,
      source: averages.source,
      isActiveToday: futureActive.has(player.playerKey),
    });

    currentLines.push(current);
    remainingLines.push(projected);
  }

  const current = sumContributions(currentLines, categories);
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
