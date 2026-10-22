// Best adds: which free agent would flip the most categories this week.
//
// This is not a port — the Python waiver code is a trend table, not a recommender — so the
// scoring is deliberately simple and explainable: simulate the add, re-run the category
// scoring, and rank by how many categories it actually turns.

import type { Feed } from "../feed/types";
import type { StatCategory, YahooPlayer } from "../yahoo/types";
import { isPercentageStat } from "./statMap";
import { playerAverages, type ProjectionMode } from "./statWindows";
import { weekGames } from "./schedule";
import { resolveNbaId } from "./playerIdentity";
import { calculateProjectedPoints, type TeamProjection, type Totals } from "./project";

export interface AddCandidate {
  playerKey: string;
  playerId: string;
  name: string;
  teamAbbr: string;
  positions: string[];
  remainingGames: number;
  /** Categories gained if this player played out the week for you. */
  categoriesGained: number;
  /** Continuous tiebreak: summed normalized margin improvement. */
  score: number;
  /** Categories this add would flip your way. */
  flips: string[];
  /** Categories it would cost you — a scorer who bleeds turnovers is not a free win. */
  costs: string[];
  status: string;
}

export interface AddsInput {
  feed: Feed;
  categories: StatCategory[];
  user: TeamProjection;
  opponent: TeamProjection;
  freeAgents: YahooPlayer[];
  weekStart: string;
  weekEnd: string;
  today: string;
  mode: ProjectionMode;
  limit?: number;
}

function addLine(totals: Totals, addition: Totals, categories: StatCategory[]): Totals {
  const merged: Totals = { ...totals };

  for (const key of ["_FGM", "_FGA", "_FTM", "_FTA"]) {
    merged[key] = (merged[key] ?? 0) + (addition[key] ?? 0);
  }
  for (const category of categories) {
    if (category.isDisplayOnly || isPercentageStat(category.displayName)) continue;
    merged[category.statId] = (merged[category.statId] ?? 0) + (addition[category.statId] ?? 0);
  }
  for (const category of categories) {
    if (category.isDisplayOnly) continue;
    if (category.displayName === "FG%") {
      merged[category.statId] = (merged["_FGA"] ?? 0) > 0 ? (merged["_FGM"] ?? 0) / (merged["_FGA"] as number) : 0;
    } else if (category.displayName === "FT%") {
      merged[category.statId] = (merged["_FTA"] ?? 0) > 0 ? (merged["_FTM"] ?? 0) / (merged["_FTA"] as number) : 0;
    }
  }
  return merged;
}

/** How much closer each category gets, scaled so categories are comparable. */
function marginScore(
  categories: StatCategory[],
  before: Totals,
  after: Totals,
  opponent: Totals,
): { score: number; flips: string[]; costs: string[] } {
  let score = 0;
  const flips: string[] = [];
  const costs: string[] = [];

  for (const category of categories) {
    if (category.isDisplayOnly) continue;

    const opponentValue = opponent[category.statId] ?? 0;
    const scale = Math.abs(opponentValue) > 0.0001 ? Math.abs(opponentValue) : 1;
    const lowerIsBetter = category.sortOrder === "0";
    const sign = lowerIsBetter ? -1 : 1;

    const beforeMargin = sign * ((before[category.statId] ?? 0) - opponentValue);
    const afterMargin = sign * ((after[category.statId] ?? 0) - opponentValue);
    score += (afterMargin - beforeMargin) / scale;

    if (beforeMargin <= 0 && afterMargin > 0) flips.push(category.displayName);
    if (beforeMargin > 0 && afterMargin <= 0) costs.push(category.displayName);
  }

  return { score, flips, costs };
}

export function rankAdds(input: AddsInput): AddCandidate[] {
  const { feed, categories, user, opponent, freeAgents, weekStart, weekEnd, today, mode } = input;

  const [baseline] = calculateProjectedPoints(categories, user.combined, opponent.combined);
  const candidates: AddCandidate[] = [];

  for (const player of freeAgents) {
    const nbaId = resolveNbaId(feed.index, player.playerId, player.name);
    const played = new Set(
      nbaId
        ? (feed.players.players[nbaId]?.games ?? [])
            .filter((row) => row[0] >= weekStart && row[0] <= today)
            .map((row) => row[0])
        : [],
    );
    const games = weekGames(feed.schedule, player.teamAbbr, weekStart, weekEnd, today, played);
    if (games.remaining === 0) continue;

    const averages = playerAverages({
      nbaId,
      mode,
      today,
      players: feed.players,
      playersPrev: feed.playersPrev,
      projections: feed.projections.players,
    });
    if (averages.source === "none") continue;

    const addition: Totals = {};
    for (const category of categories) {
      if (category.isDisplayOnly) continue;
      const field = category.displayName;
      if (isPercentageStat(field)) continue;
      addition[category.statId] = 0;
    }

    // Reuse the same line-building rules as the projection by scaling the averages here.
    const line = averages.stats;
    addition["_FGM"] = line.fgm * games.remaining;
    addition["_FGA"] = line.fga * games.remaining;
    addition["_FTM"] = line.ftm * games.remaining;
    addition["_FTA"] = line.fta * games.remaining;
    for (const category of categories) {
      if (category.isDisplayOnly || isPercentageStat(category.displayName)) continue;
      const map: Record<string, number> = {
        "3PTM": line.threes, "3PM": line.threes,
        PTS: line.points, Points: line.points,
        REB: line.rebounds, Rebounds: line.rebounds,
        AST: line.assists, Assists: line.assists,
        ST: line.steals, STL: line.steals, Steals: line.steals,
        BLK: line.blocks, Blocks: line.blocks,
        TO: line.turnovers, Turnovers: line.turnovers,
      };
      addition[category.statId] = (map[category.displayName] ?? 0) * games.remaining;
    }

    const after = addLine(user.combined, addition, categories);
    const [withAdd] = calculateProjectedPoints(categories, after, opponent.combined);
    const { score, flips, costs } = marginScore(categories, user.combined, after, opponent.combined);

    candidates.push({
      playerKey: player.playerKey,
      playerId: player.playerId,
      name: player.name,
      teamAbbr: player.teamAbbr,
      positions: player.eligiblePositions,
      remainingGames: games.remaining,
      categoriesGained: withAdd.win - baseline.win,
      score,
      flips,
      costs,
      status: player.status,
    });
  }

  candidates.sort((a, b) => b.categoriesGained - a.categoriesGained || b.score - a.score);
  return candidates.slice(0, input.limit ?? 8);
}
