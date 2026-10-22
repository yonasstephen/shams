// A player's recent form the way the web app's waiver table shows it: stats over the last
// N games or the last N days, averaged or summed, with minutes and the minute trend.
//
// Mirrors tools/player/player_stats.compute_player_stats (windows, aggregation, minutes)
// and tools/player/player_minutes_trend.compute_minute_trend (trend). Windows read the
// feed's raw game-log tail, so they reach back `tail_days` at most; "season" reads the
// feed's precomputed season average instead.

import type { GameRow, PlayerEntry, StatLine } from "../feed/types";
import { isoDaysBefore } from "./statWindows";

export type FormWindow = "last" | "last3" | "last7" | "last7d" | "last14d" | "last30d" | "season";

export const FORM_WINDOWS: FormWindow[] = ["last", "last3", "last7", "last7d", "last14d", "last30d", "season"];

export const FORM_WINDOW_LABELS: Record<FormWindow, string> = {
  last: "Last game",
  last3: "Last 3 games",
  last7: "Last 7 games",
  last7d: "Last 7 days",
  last14d: "Last 14 days",
  last30d: "Last 30 days",
  season: "Season",
};

export type Aggregation = "avg" | "sum";

export interface MinuteTrend {
  /** Minutes in his most recent game. */
  last: number;
  /** Average over up to three games before it; 0 when there are none, as in Python. */
  priorAverage: number;
  delta: number;
}

export interface PlayerForm {
  /** Null when the window holds no games. */
  stats: StatLine | null;
  minutes: number | null;
  /** Games in the window, counting the ones he sat: the web app's denominator. */
  games: number;
  /** How many of those he sat. Null for a season average, which does not say. */
  dnp: number | null;
  /** His most recent game with minutes on the clock. */
  lastPlayed: string | null;
  trend: MinuteTrend | null;
  source: "window" | "season" | "previous" | "none";
}

export interface FormInput {
  entry: PlayerEntry | undefined;
  /** Last season's entry, for the season window before this season has a game. */
  previous: PlayerEntry | undefined;
  window: FormWindow;
  aggregation: Aggregation;
  today: string;
}

const COLUMNS = {
  fgm: 2, fga: 3, ftm: 4, fta: 5, threes: 6, points: 7,
  rebounds: 8, assists: 9, steals: 10, blocks: 11, turnovers: 12,
} as const;

const COUNTING_FIELDS = Object.keys(COLUMNS) as (keyof typeof COLUMNS)[];

/** Box scores list a game he sat with blank minutes, which the feed carries as 0. */
export function playedIn(row: GameRow): boolean {
  return row[1] > 0;
}

function newestFirst(games: GameRow[], today: string): GameRow[] {
  return games.filter((row) => row[0] <= today).sort((a, b) => (a[0] < b[0] ? 1 : a[0] > b[0] ? -1 : 0));
}

/** The rows a window covers, newest first. Day windows include the cutoff day, as Python's do. */
export function windowRows(games: GameRow[], window: Exclude<FormWindow, "season">, today: string): GameRow[] {
  const recent = newestFirst(games, today);
  if (window === "last") return recent.slice(0, 1);

  const match = /^last(\d+)(d?)$/.exec(window);
  if (!match) return [];
  const size = Number(match[1]);
  if (match[2] === "d") {
    const cutoff = isoDaysBefore(today, size);
    return recent.filter((row) => row[0] >= cutoff);
  }
  return recent.slice(0, size);
}

/** Minutes in the latest game against the average of the three before it.
 *
 * Python reads the last four games that have a minutes value, which skips the ones he
 * sat; skipping zero-minute rows is the same rule on the feed's numbers. */
export function minuteTrend(games: GameRow[], today: string): MinuteTrend | null {
  const played = newestFirst(games, today).filter(playedIn).slice(0, 4);
  const [latest, ...prior] = played;
  if (!latest) return null;

  const priorAverage = prior.length ? prior.reduce((sum, row) => sum + row[1], 0) / prior.length : 0;
  return { last: latest[1], priorAverage, delta: latest[1] - priorAverage };
}

function aggregate(rows: GameRow[], aggregation: Aggregation): { stats: StatLine; minutes: number } {
  const divisor = aggregation === "avg" ? rows.length : 1;
  const totals = Object.fromEntries(COUNTING_FIELDS.map((field) => [field, 0])) as Record<keyof typeof COLUMNS, number>;
  let minutes = 0;
  for (const row of rows) {
    minutes += row[1];
    for (const field of COUNTING_FIELDS) totals[field] += row[COLUMNS[field]];
  }

  const stats = { games_played: rows.length } as StatLine;
  for (const field of COUNTING_FIELDS) stats[field] = totals[field] / divisor;
  // Percentages from summed volume, never from averaged per-game percentages.
  stats.fg_pct = totals.fga > 0 ? totals.fgm / totals.fga : 0;
  stats.ft_pct = totals.fta > 0 ? totals.ftm / totals.fta : 0;
  return { stats, minutes: minutes / divisor };
}

function fromSeasonAverage(average: StatLine, aggregation: Aggregation): { stats: StatLine; minutes: number | null } {
  const games = average.games_played ?? 0;
  const scale = aggregation === "avg" ? 1 : games;
  const stats: StatLine = { ...average };
  for (const field of COUNTING_FIELDS) stats[field] = (average[field] ?? 0) * scale;
  return { stats, minutes: average.mpg === undefined ? null : average.mpg * scale };
}

export function playerForm(input: FormInput): PlayerForm {
  const { entry, previous, window, aggregation, today } = input;
  const games = entry?.games ?? [];
  const lastPlayed = newestFirst(games, today).find(playedIn)?.[0] ?? null;
  const trend = minuteTrend(games, today);

  if (window === "season") {
    for (const [average, source] of [
      [entry?.season_avg, "season"],
      [previous?.season_avg, "previous"],
    ] as const) {
      if (average && (average.games_played ?? 0) > 0) {
        return { ...fromSeasonAverage(average, aggregation), games: average.games_played ?? 0, dnp: null, lastPlayed, trend, source };
      }
    }
    return { stats: null, minutes: null, games: 0, dnp: null, lastPlayed, trend, source: "none" };
  }

  const rows = windowRows(games, window, today);
  if (!rows.length) {
    return { stats: null, minutes: null, games: 0, dnp: 0, lastPlayed, trend, source: entry ? "window" : "none" };
  }

  return {
    ...aggregate(rows, aggregation),
    games: rows.length,
    dnp: rows.filter((row) => !playedIn(row)).length,
    lastPlayed,
    trend,
    source: "window",
  };
}
