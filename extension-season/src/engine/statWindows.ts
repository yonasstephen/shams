// Per-game averages over a window of games, computed in the browser from the feed's raw
// game-log tail. Windows are measured against the day this runs, not the day the feed was
// built, so a stale feed still produces the right last7d/last30d.
//
// Mirrors tools/player/player_stats.compute_player_stats with agg_mode="avg".

import type { GameRow, PlayerEntry, PlayersFile, ProjectionEntry, StatLine } from "../feed/types";

export type ProjectionMode = "season" | "last3" | "last7" | "last7d" | "last30d";

export const PROJECTION_MODES: ProjectionMode[] = ["season", "last3", "last7", "last7d", "last30d"];

export const MODE_LABELS: Record<ProjectionMode, string> = {
  season: "Season averages",
  last3: "Last 3 games",
  last7: "Last 7 games",
  last7d: "Last 7 days",
  last30d: "Last 30 days",
};

/** Where a player's numbers came from, so the overlay can be honest about it. */
export type StatSource = "window" | "season" | "projection" | "previous" | "none";

export interface PlayerAverages {
  stats: StatLine;
  source: StatSource;
  gamesInSample: number;
}

const EMPTY: StatLine = {
  fgm: 0, fga: 0, fg_pct: 0, ftm: 0, fta: 0, ft_pct: 0, threes: 0,
  points: 0, rebounds: 0, assists: 0, steals: 0, blocks: 0, turnovers: 0,
};

function parseMode(mode: ProjectionMode): { games: number | null; days: number | null } {
  if (mode === "season") return { games: null, days: null };
  const match = /^last(\d+)(d?)$/.exec(mode);
  if (!match) return { games: null, days: null };
  const size = Number(match[1]);
  return match[2] === "d" ? { games: null, days: size } : { games: size, days: null };
}

function isoDaysBefore(today: string, days: number): string {
  const date = new Date(`${today}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() - days);
  return date.toISOString().slice(0, 10);
}

function averageRows(rows: GameRow[]): StatLine {
  if (!rows.length) return { ...EMPTY };

  const totals = { fgm: 0, fga: 0, ftm: 0, fta: 0, threes: 0, points: 0, rebounds: 0, assists: 0, steals: 0, blocks: 0, turnovers: 0 };
  for (const row of rows) {
    totals.fgm += row[2];
    totals.fga += row[3];
    totals.ftm += row[4];
    totals.fta += row[5];
    totals.threes += row[6];
    totals.points += row[7];
    totals.rebounds += row[8];
    totals.assists += row[9];
    totals.steals += row[10];
    totals.blocks += row[11];
    totals.turnovers += row[12];
  }

  const n = rows.length;
  return {
    fgm: totals.fgm / n,
    fga: totals.fga / n,
    // Percentages come from summed volume, never from averaged per-game percentages.
    fg_pct: totals.fga > 0 ? totals.fgm / totals.fga : 0,
    ftm: totals.ftm / n,
    fta: totals.fta / n,
    ft_pct: totals.fta > 0 ? totals.ftm / totals.fta : 0,
    threes: totals.threes / n,
    points: totals.points / n,
    rebounds: totals.rebounds / n,
    assists: totals.assists / n,
    steals: totals.steals / n,
    blocks: totals.blocks / n,
    turnovers: totals.turnovers / n,
    games_played: n,
  };
}

/** Games a player has already logged inside [start, end], for the banked half of a week. */
export function gamesInRange(entry: PlayerEntry | undefined, start: string, end: string): GameRow[] {
  if (!entry) return [];
  return entry.games.filter((row) => row[0] >= start && row[0] <= end);
}

export function sumRows(rows: GameRow[]): StatLine {
  const averages = averageRows(rows);
  const n = rows.length || 1;
  if (!rows.length) return { ...EMPTY, games_played: 0 };
  return {
    ...averages,
    fgm: averages.fgm * n,
    fga: averages.fga * n,
    ftm: averages.ftm * n,
    fta: averages.fta * n,
    threes: averages.threes * n,
    points: averages.points * n,
    rebounds: averages.rebounds * n,
    assists: averages.assists * n,
    steals: averages.steals * n,
    blocks: averages.blocks * n,
    turnovers: averages.turnovers * n,
    games_played: rows.length,
  };
}

export interface AveragesInput {
  nbaId: string | null;
  mode: ProjectionMode;
  today: string;
  players: PlayersFile;
  playersPrev: PlayersFile;
  projections: Record<string, ProjectionEntry>;
  /** Below this many current-season games, fall back to the preseason projection. */
  minSampleGames?: number;
}

/** A player's per-game averages, with the fallback chain the early season needs:
 *  requested window -> season to date -> preseason projection -> last season -> zeros. */
export function playerAverages(input: AveragesInput): PlayerAverages {
  const { nbaId, mode, today, players, playersPrev, projections } = input;
  const minSample = input.minSampleGames ?? 3;
  if (!nbaId) return { stats: { ...EMPTY }, source: "none", gamesInSample: 0 };

  const entry = players.players[nbaId];
  const { games, days } = parseMode(mode);

  if (entry && (games !== null || days !== null)) {
    const sorted = entry.games.slice().sort((a, b) => (a[0] < b[0] ? 1 : -1));
    let window: GameRow[];
    if (days !== null) {
      const cutoff = isoDaysBefore(today, days);
      window = sorted.filter((row) => row[0] >= cutoff && row[0] <= today);
    } else {
      window = sorted.filter((row) => row[0] <= today).slice(0, games ?? 0);
    }
    if (window.length) {
      return { stats: averageRows(window), source: "window", gamesInSample: window.length };
    }
  }

  const seasonGames = entry?.season_avg?.games_played ?? 0;
  if (entry?.season_avg && seasonGames >= minSample) {
    return { stats: entry.season_avg, source: "season", gamesInSample: seasonGames };
  }

  const projected = projections[nbaId];
  if (projected) {
    return { stats: projected.stats, source: "projection", gamesInSample: 0 };
  }

  const previous = playersPrev.players[nbaId];
  if (previous?.season_avg) {
    return {
      stats: previous.season_avg,
      source: "previous",
      gamesInSample: previous.season_avg.games_played ?? 0,
    };
  }

  if (entry?.season_avg) {
    return { stats: entry.season_avg, source: "season", gamesInSample: seasonGames };
  }

  return { stats: { ...EMPTY }, source: "none", gamesInSample: 0 };
}
