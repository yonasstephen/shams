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
  numTeams: number | null;
  /** First and last day of the fantasy season, YYYY-MM-DD; empty when Yahoo omits them. */
  startDate: string;
  endDate: string;
  /** Last day trades can be made, YYYY-MM-DD. */
  tradeEndDate: string;
  playoffStartWeek: number | null;
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

/** One team's roster as part of a league-wide fetch. */
export interface LeagueRoster {
  teamKey: string;
  teamId: string;
  name: string;
  manager: string;
  players: YahooPlayer[];
}

export interface Matchup {
  week: number;
  weekStart: string;
  weekEnd: string;
  teams: YahooTeam[];
}
