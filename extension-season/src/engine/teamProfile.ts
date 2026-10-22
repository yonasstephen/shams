// Team strengths across the league — the Shams answer to Yahoo Plus's Trade Hub.
//
// Yahoo grades teams by roster slot. In a categories league what matters is which
// categories a team wins, so this plays every roster out over the rest of the season — the
// real schedule, a best lineup every day, the league's own categories — and ranks each team
// in each category. Slot strength stays as a secondary view, because positions still decide
// who can start.

import type { Feed, StatLine } from "../feed/types";
import type { LeagueRoster, StatCategory } from "../yahoo/types";
import { applyPercentages, lineToStats, type Totals } from "./project";
import { resolveNbaId } from "./playerIdentity";
import { datesInRange, gameDatesFor } from "./schedule";
import { isPercentageStat } from "./statMap";
import {
  playerAverages,
  restOfSeasonAverages,
  type PlayerAverages,
  type ProjectionMode,
  type StatSource,
} from "./statWindows";
import { buildValuationContext, totalValue, valuePlayer, type CategoryZ } from "./valuation";
import { bestLineup } from "./lineup";
import { INACTIVE_POSITIONS } from "./rosterOptimizer";

/** "ros" is the rest-of-season blend; the rest are the matchup panel's fixed windows. */
export type ProfileMode = "ros" | ProjectionMode;

export type Grade = "strong" | "neutral" | "weak";

/** Slots that hold injured players. They are rostered, but nobody's lineup includes them. */
const INJURED_SLOTS = new Set(["IL", "IL+"]);

/** How many categories a team's needs list holds — the same count Yahoo shows. */
export const NEED_COUNT = 3;

export interface ProfiledPlayer {
  playerKey: string;
  playerId: string;
  name: string;
  teamAbbr: string;
  eligiblePositions: string[];
  selectedPosition: string;
  status: string;
  nbaId: string | null;
  source: StatSource;
  perGame: StatLine;
  z: CategoryZ;
  value: number;
  /** NBA games left in the horizon, and how many of them he starts in the simulation. */
  gamesLeft: number;
  starts: number;
  /** In an IL slot, so left out of every lineup. */
  injured: boolean;
}

export interface CategoryStanding {
  statId: string;
  displayName: string;
  /** Expected weekly total; a rate for FG%/FT%. */
  weekly: number;
  rank: number;
  /** Share of the other teams this team beats in the category. */
  winShare: number;
  grade: Grade;
}

export interface SlotStanding {
  slot: string;
  /** Value above the league's worst rostered player, summed over this slot's starts, per week. */
  value: number;
  rank: number;
  grade: Grade;
}

export interface TeamProfile {
  teamKey: string;
  teamId: string;
  name: string;
  manager: string;
  players: ProfiledPlayer[];
  weekly: Totals;
  categories: CategoryStanding[];
  slots: SlotStanding[];
  /** Sum of win shares: categories won against a random league opponent in an average week. */
  expectedWins: number;
  rank: number;
  /** Weakest categories first, padded with neutral ones — Yahoo's needs rule, on categories. */
  needs: CategoryStanding[];
  /** Rostered players with no stats to project. */
  unmatched: number;
}

export interface LeagueProfile {
  mode: ProfileMode;
  horizon: { start: string; end: string; days: number; weeks: number };
  categories: { statId: string; displayName: string; lowerIsBetter: boolean }[];
  slotTypes: string[];
  /** Best first. */
  teams: TeamProfile[];
}

export interface ProfileInput {
  feed: Feed;
  categories: StatCategory[];
  /** The league's slots, one entry per slot (["PG", "SG", …, "BN", "BN", "IL"]). */
  rosterPositions: string[];
  rosters: LeagueRoster[];
  today: string;
  horizonStart: string;
  horizonEnd: string;
  mode: ProfileMode;
}

const SHOOTING_KEYS = ["_FGM", "_FGA", "_FTM", "_FTA"] as const;
const EPSILON = 1e-9;

/** Top third strong, bottom third weak, the middle neutral; under three teams, all neutral. */
export function gradeFor(rank: number, teamCount: number): Grade {
  const third = Math.floor(teamCount / 3);
  if (third > 0 && rank <= third) return "strong";
  if (third > 0 && rank > teamCount - third) return "weak";
  return "neutral";
}

/** Rank (1 = best, ties share a rank) and win share of each value against all the others. */
export function standings(values: number[], lowerIsBetter: boolean): { rank: number; winShare: number }[] {
  const others = values.length - 1;
  return values.map((value, index) => {
    let better = 0;
    let beats = 0;
    let ties = 0;
    values.forEach((other, otherIndex) => {
      if (otherIndex === index) return;
      const diff = lowerIsBetter ? other - value : value - other;
      if (Math.abs(diff) <= EPSILON) ties += 1;
      else if (diff > 0) beats += 1;
      else better += 1;
    });
    return { rank: better + 1, winShare: others > 0 ? (beats + ties / 2) / others : 0 };
  });
}

function averagesFor(input: ProfileInput, nbaId: string | null): PlayerAverages {
  const { feed, mode, today } = input;
  const sources = {
    nbaId,
    players: feed.players,
    playersPrev: feed.playersPrev,
    projections: feed.projections.players,
  };
  return mode === "ros" ? restOfSeasonAverages(sources) : playerAverages({ ...sources, mode, today });
}

export function profileLeague(input: ProfileInput): LeagueProfile {
  const { feed, categories, rosterPositions, rosters } = input;
  const scoring = categories.filter((category) => !category.isDisplayOnly);
  const slotTypes = [...new Set(rosterPositions.filter((slot) => !INACTIVE_POSITIONS.has(slot)))];

  const dates = input.horizonStart <= input.horizonEnd ? datesInRange(input.horizonStart, input.horizonEnd) : [];
  const weeks = dates.length / 7;

  // Every rostered player, valued against every other rostered player.
  const teamsPlayers = rosters.map((roster) =>
    roster.players.map((player) => {
      const nbaId = resolveNbaId(feed.index, player.playerId, player.name);
      return { player, nbaId, averages: averagesFor(input, nbaId) };
    }),
  );
  const pool = teamsPlayers.flat().filter((entry) => entry.averages.source !== "none");
  const context = buildValuationContext(pool.map((entry) => entry.averages.stats), categories);
  const valueOf = (averages: PlayerAverages) => {
    const z = averages.source === "none" ? {} : valuePlayer(averages.stats, context);
    return { z, value: totalValue(z) };
  };

  // Slot strength is measured above the worst rostered player. Raw z is centred on the
  // average rostered player, so a below-average starter scores below zero and an empty
  // slot (zero) would outrank a filled one.
  const replacement = pool.length ? Math.min(...pool.map((entry) => valueOf(entry.averages).value)) : 0;

  const gameDatesByTeam = new Map<string, Set<string>>();
  const gameDates = (teamAbbr: string): Set<string> => {
    let found = gameDatesByTeam.get(teamAbbr);
    if (!found) {
      found = dates.length ? new Set(gameDatesFor(feed.schedule, teamAbbr, input.horizonStart, input.horizonEnd)) : new Set();
      gameDatesByTeam.set(teamAbbr, found);
    }
    return found;
  };

  const partial = rosters.map((roster, teamIndex) => {
    const players: ProfiledPlayer[] = (teamsPlayers[teamIndex] ?? []).map(({ player, nbaId, averages }) => {
      const { z, value } = valueOf(averages);
      return {
        playerKey: player.playerKey,
        playerId: player.playerId,
        name: player.name,
        teamAbbr: player.teamAbbr,
        eligiblePositions: player.eligiblePositions,
        selectedPosition: player.selectedPosition,
        status: player.status,
        nbaId,
        source: averages.source,
        perGame: averages.stats,
        z,
        value,
        gamesLeft: gameDates(player.teamAbbr).size,
        starts: 0,
        injured: INJURED_SLOTS.has(player.selectedPosition),
      };
    });

    const available = players.filter((player) => !player.injured && player.source !== "none");
    const lines = new Map(available.map((player) => [player.playerKey, lineToStats(player.perGame, categories, 1)]));
    const byKey = new Map(players.map((player) => [player.playerKey, player]));

    const totals: Totals = {};
    for (const key of SHOOTING_KEYS) totals[key] = 0;
    for (const category of scoring) totals[category.statId] = 0;
    const slotValue: Record<string, number> = Object.fromEntries(slotTypes.map((slot) => [slot, 0]));

    // Most days share a handful of distinct "who has a game" sets, so lineups are cached.
    const lineups = new Map<string, Map<string, string>>();
    for (const date of dates) {
      const playing = available.filter((player) => gameDates(player.teamAbbr).has(date));
      if (!playing.length) continue;

      const signature = playing.map((player) => player.playerKey).join("|");
      let lineup = lineups.get(signature);
      if (!lineup) {
        lineup = bestLineup(
          playing.map((player) => ({ key: player.playerKey, eligiblePositions: player.eligiblePositions, value: player.value })),
          rosterPositions,
        );
        lineups.set(signature, lineup);
      }

      for (const [playerKey, slot] of lineup) {
        const line = lines.get(playerKey);
        const starter = byKey.get(playerKey);
        if (!line || !starter) continue;
        starter.starts += 1;
        slotValue[slot] = (slotValue[slot] ?? 0) + starter.value - replacement;
        for (const key of SHOOTING_KEYS) totals[key] = (totals[key] ?? 0) + (line[key] ?? 0);
        for (const category of scoring) {
          if (isPercentageStat(category.displayName)) continue;
          totals[category.statId] = (totals[category.statId] ?? 0) + (line[category.statId] ?? 0);
        }
      }
    }

    // Per week, so the numbers read like a matchup; percentages are rates and come last.
    const weekly: Totals = {};
    for (const [key, value] of Object.entries(totals)) weekly[key] = weeks > 0 ? value / weeks : 0;
    applyPercentages(weekly, categories);

    return {
      roster,
      players: players.sort((a, b) => b.value - a.value),
      weekly,
      slotValue: Object.fromEntries(
        Object.entries(slotValue).map(([slot, value]) => [slot, weeks > 0 ? value / weeks : 0]),
      ),
      unmatched: players.filter((player) => player.source === "none").length,
    };
  });

  const teamCount = partial.length;
  const categoryStandings = scoring.map((category) =>
    standings(
      partial.map((team) => team.weekly[category.statId] ?? 0),
      category.sortOrder === "0",
    ),
  );
  const slotStandings = slotTypes.map((slot) =>
    standings(partial.map((team) => team.slotValue[slot] ?? 0), false),
  );

  const teams: TeamProfile[] = partial.map((team, teamIndex) => {
    const categoryRows: CategoryStanding[] = scoring.map((category, categoryIndex) => {
      const standing = categoryStandings[categoryIndex]?.[teamIndex] ?? { rank: teamCount, winShare: 0 };
      return {
        statId: category.statId,
        displayName: category.displayName,
        weekly: team.weekly[category.statId] ?? 0,
        rank: standing.rank,
        winShare: standing.winShare,
        grade: gradeFor(standing.rank, teamCount),
      };
    });

    const slotRows: SlotStanding[] = slotTypes.map((slot, slotIndex) => {
      const standing = slotStandings[slotIndex]?.[teamIndex] ?? { rank: teamCount, winShare: 0 };
      return { slot, value: team.slotValue[slot] ?? 0, rank: standing.rank, grade: gradeFor(standing.rank, teamCount) };
    });

    const worstFirst = (grade: Grade) =>
      categoryRows.filter((row) => row.grade === grade).sort((a, b) => b.rank - a.rank);

    return {
      teamKey: team.roster.teamKey,
      teamId: team.roster.teamId,
      name: team.roster.name,
      manager: team.roster.manager,
      players: team.players,
      weekly: team.weekly,
      categories: categoryRows,
      slots: slotRows,
      expectedWins: categoryRows.reduce((sum, row) => sum + row.winShare, 0),
      rank: 0,
      needs: [...worstFirst("weak"), ...worstFirst("neutral")].slice(0, NEED_COUNT),
      unmatched: team.unmatched,
    };
  });

  const overall = standings(teams.map((team) => team.expectedWins), false);
  teams.forEach((team, index) => {
    team.rank = overall[index]?.rank ?? teamCount;
  });
  teams.sort((a, b) => a.rank - b.rank || a.name.localeCompare(b.name));

  return {
    mode: input.mode,
    horizon: { start: input.horizonStart, end: input.horizonEnd, days: dates.length, weeks },
    categories: scoring.map((category) => ({
      statId: category.statId,
      displayName: category.displayName,
      lowerIsBetter: category.sortOrder === "0",
    })),
    slotTypes,
    teams,
  };
}
