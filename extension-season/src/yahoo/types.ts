export interface StatCategory {
  statId: string;
  name: string;
  displayName: string;
  /** Yahoo's sort_order: "0" means lower is better (turnovers). */
  sortOrder: string;
  isDisplayOnly: boolean;
}

export interface RosterPosition {
  position: string;
  count: number;
}

export interface LeagueSettings {
  leagueKey: string;
  name: string;
  statCategories: StatCategory[];
  rosterPositions: RosterPosition[];
  currentWeek: number | null;
  startWeek: number | null;
  endWeek: number | null;
}

export interface YahooPlayer {
  playerKey: string;
  playerId: string;
  name: string;
  /** NBA team abbreviation as Yahoo spells it, e.g. "GSW". */
  teamAbbr: string;
  selectedPosition: string;
  eligiblePositions: string[];
  status: string;
  /** Per-stat-id values, present only when the request asked for stats. */
  stats?: Record<string, number>;
}

export interface YahooTeam {
  teamKey: string;
  teamId: string;
  name: string;
  /** Week totals Yahoo itself shows, per stat id. */
  stats?: Record<string, number>;
}

export interface Matchup {
  week: number;
  weekStart: string;
  weekEnd: string;
  teams: YahooTeam[];
}
