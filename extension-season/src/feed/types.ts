// Shapes of the files written by scripts/build_feed.py. Keep in step with
// SCHEMA_VERSION there — meta.schema is checked at load time.

export const FEED_SCHEMA = 1;

export interface FeedMeta {
  schema: number;
  season: string;
  previous_season: string;
  generated_at: string;
  counts: Record<string, number>;
  files: Record<string, { bytes: number; raw_bytes: number; sha256: string }>;
}

/** Per-game averages. Field names match the box-score cache, so the Python and TS
 *  sides read the same words for the same numbers. */
export interface StatLine {
  games_played?: number;
  gp?: number;
  /** Minutes per game. Season averages carry it only in feeds built since it was added. */
  mpg?: number;
  fgm: number;
  fga: number;
  fg_pct: number;
  ftm: number;
  fta: number;
  ft_pct: number;
  threes: number;
  points: number;
  rebounds: number;
  assists: number;
  steals: number;
  blocks: number;
  turnovers: number;
}

export interface ProjectionEntry {
  name: string;
  team: string;
  positions: string;
  stats: StatLine;
  confidence: number;
  yahoo_id?: string;
}

export interface ProjectionsFile {
  season: string;
  count: number;
  players: Record<string, ProjectionEntry>;
}

/** One game log row, positional, in `PlayersFile.fields` order. */
export type GameRow = [
  date: string,
  min: number,
  fgm: number,
  fga: number,
  ftm: number,
  fta: number,
  threes: number,
  points: number,
  rebounds: number,
  assists: number,
  steals: number,
  blocks: number,
  turnovers: number,
];

export interface PlayerEntry {
  name: string;
  games: GameRow[];
  season_avg?: StatLine;
  eligible_positions?: string[];
}

export interface PlayersFile {
  season: string;
  tail_days: number;
  tail_start: string;
  fields: string[];
  count: number;
  players: Record<string, PlayerEntry>;
}

/** `[homeTricode, awayTricode, gameId, postponedStatus]`. */
export type ScheduleRow = [home: string, away: string, gameId: string, postponed: string];

export interface ScheduleFile {
  season: string;
  fields: string[];
  game_count: number;
  dates: Record<string, ScheduleRow[]>;
}

export interface PlayerIndexFile {
  count: number;
  name_count?: number;
  yahoo_to_nba: Record<string, string>;
  /** Normalized name -> NBA id, the fallback when a Yahoo id was never indexed. */
  name_to_nba?: Record<string, string>;
  nba_names: Record<string, string>;
}

export interface Feed {
  meta: FeedMeta;
  projections: ProjectionsFile;
  players: PlayersFile;
  playersPrev: PlayersFile;
  schedule: ScheduleFile;
  index: PlayerIndexFile;
}

export interface FeedStatus {
  state: "ready" | "empty" | "error";
  season?: string;
  generatedAt?: string;
  fetchedAt?: string;
  error?: string;
}
