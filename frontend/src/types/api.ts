/**
 * API type definitions
 */

export interface PlayerStats {
  fg_pct: number;
  ft_pct: number;
  fgm: number;
  fga: number;
  ftm: number;
  fta: number;
  threes: number;
  points: number;
  rebounds: number;
  assists: number;
  steals: number;
  blocks: number;
  turnovers: number;
  usage_pct: number;
  games_count: number;
  games_started: number;
  minutes: number;
  last_game_date?: string | null;
}

export interface GameLog {
  date: string;
  matchup: string;
  fantasy_week?: number | null;
  wl?: string | null;  // "W" or "L" for win/loss
  score?: string | null;  // Score in format "101-98"
  minutes: number;
  fg_pct: number;
  ft_pct: number;
  fgm: number;
  fga: number;
  ftm: number;
  fta: number;
  threes: number;
  points: number;
  rebounds: number;
  assists: number;
  steals: number;
  blocks: number;
  turnovers: number;
  usage_pct: number;
}

export interface PlayerStatsResponse {
  player_id: number;
  player_name: string;
  team_tricode: string | null;
  rank?: number | null;
  last_game: PlayerStats | null;
  last3: PlayerStats | null;
  last7: PlayerStats | null;
  season: PlayerStats | null;
  trend: number;
  recent_games: GameLog[];
  upcoming_games: GameLog[];
  current_week_remaining_games: number;
}

export interface PlayerSuggestion {
  player_id: number;
  full_name: string;
  first_name: string;
  last_name: string;
}

export interface PlayerSearchResponse {
  suggestions: PlayerSuggestion[];
  exact_match: boolean;
}

export interface WaiverPlayer {
  name: string;
  player_id?: number | null;
  rank?: number | null;
  trend: number;
  minutes: number;
  status: string;
  injury_status: string;
  injury_note: string;
  stats: PlayerStats | null;
  last_game_date?: string | null;
  remaining_games: number;
  total_games: number;
  next_week_games: number;
  has_back_to_back: boolean;
}

export interface WaiverCacheInfo {
  timestamp?: string;
  age_hours?: number;
  player_count?: number;
}

export interface WaiverResponse {
  players: WaiverPlayer[];
  total_count: number;
  stats_mode: string;
  agg_mode: string;
  current_week: number;
  cache_info?: WaiverCacheInfo | null;
}

export interface MatchupTeam {
  team_name: string;
  team_key: string;
  team_points: number;
  projected_team_points: number;
  team_ties: number;
  projected_team_ties: number;
}

export interface PlayerContribution {
  player_key: string;
  player_name: string;
  player_id?: number | null;
  total_games: number;
  remaining_games: number;
  games_played: number;
  stats: Record<string, number>;
  shooting: Record<string, number>;
  is_on_roster_today: boolean;
}

export interface MatchupProjectionResponse {
  week: number;
  week_start: string;
  week_end: string;
  user_team: MatchupTeam;
  opponent_team: MatchupTeam;
  stat_categories: any[];
  user_current: Record<string, number>;
  user_projection: Record<string, number>;
  opponent_current: Record<string, number>;
  opponent_projection: Record<string, number>;
  current_player_contributions: PlayerContribution[];  // Roster contributions (actual stats so far)
  opponent_current_player_contributions: PlayerContribution[];
  player_contributions: PlayerContribution[];  // Remaining projections (projected stats for remaining games)
  opponent_player_contributions: PlayerContribution[];
  remaining_days_projection: Record<string, Record<string, Record<string, number>>>;
  player_positions: Record<string, Record<string, string>>;
  opponent_remaining_days_projection: Record<string, Record<string, Record<string, number>>>;
  opponent_player_positions: Record<string, Record<string, string>>;
  projection_mode: string;
  optimize_user_roster?: boolean;
  optimize_opponent_roster?: boolean;
}

export interface LeagueMatchup {
  week: number;
  week_start: string;
  week_end: string;
  teams: MatchupTeam[];
  stat_categories: any[];
}

export interface AllMatchupsResponse {
  league_name: string;
  week: number;
  matchups: LeagueMatchup[];
  user_team_key: string;
}

export interface LeagueInfo {
  name: string;
  league_key: string;
  league_id: string;
  season: string;
  game_code: string;
}

export interface LeagueSettingsResponse {
  current_week: number;
  total_weeks: number;
}

export interface UserResponse {
  authenticated: boolean;
  leagues: LeagueInfo[];
}

export interface DefaultLeagueResponse {
  league_key: string | null;
}

export interface SetDefaultLeagueRequest {
  league_key: string;
}

export interface RefreshOptions {
  box_scores: boolean;
  waiver_cache: boolean;
  leagues: boolean;
  player_index: boolean;  // Combined: rebuild_player_indexes + player_rankings
  league_key?: string | null;
}

export interface RefreshProgressEvent {
  type: 'status' | 'complete' | 'done' | 'error';
  message: string;
  data?: any;
}

export interface GameFileInfo {
  filename: string;
  game_id: string;
  game_date: string;
  season: string;
  matchup: string | null;
  home_team: string | null;
  away_team: string | null;
  home_score: number | null;
  away_score: number | null;
  box_score: Record<string, any> | null;
}

export interface ScheduleFileInfo {
  filename: string;
  team_id: number;
  season: string;
  games_count: number;
}

export interface PlayerSeasonStats {
  filename: string;
  player_id: number;
  player_name: string;
  stats: Record<string, number>;
  last_updated: string;
}

export interface CacheDebugResponse {
  boxscore_cache: {
    cache_dir: string;
    total_games: number;
    total_players: number;
    games_by_season: Record<string, GameFileInfo[]>;
    player_files: string[];
    player_files_count: number;
    season_stats_by_season: Record<string, PlayerSeasonStats[]>;
    date_range: {
      start: string | null;
      end: string | null;
    };
  };
  schedule_cache: {
    cache_dir: string;
    total_schedules: number;
    schedules_by_season: Record<string, ScheduleFileInfo[]>;
    player_index_by_season: Record<string, string[]>;
    total_player_indexes: number;
  };
  metadata: {
    season: string;
    last_updated: string | null;
    games_cached: number;
    players_indexed: number;
    date_range: {
      start: string | null;
      end: string | null;
    };
  };
}

export interface BoxScoreDate {
  date: string;
  game_count: number;
}

export interface LatestDateResponse {
  date: string;
  season: string;
}

export interface PlayerBoxScore {
  PLAYER_ID: number;
  PLAYER_NAME: string;
  TEAM_ID: number;
  teamTricode?: string | null;
  MIN?: string | null;
  FGM?: number | null;
  FGA?: number | null;
  FG_PCT?: number | null;
  FG3M?: number | null;
  FG3A?: number | null;
  FG3_PCT?: number | null;
  FTM?: number | null;
  FTA?: number | null;
  FT_PCT?: number | null;
  OREB?: number | null;
  DREB?: number | null;
  REB?: number | null;
  AST?: number | null;
  STL?: number | null;
  BLK?: number | null;
  TO?: number | null;
  PF?: number | null;
  PTS?: number | null;
  PLUS_MINUS?: number | null;
  USG_PCT?: number | null;
}

export interface GameBoxScore {
  game_id: string;
  game_date: string;
  season: string;
  matchup?: string | null;
  home_team?: number | null;
  away_team?: number | null;
  home_team_name?: string | null;
  away_team_name?: string | null;
  home_team_tricode?: string | null;
  away_team_tricode?: string | null;
  home_score?: number | null;
  away_score?: number | null;
  box_score: Record<string, PlayerBoxScore>;
  is_scheduled?: boolean;  // True for future games from schedule
  game_time?: string | null;  // Game start time for scheduled games
  postponed_status?: string | null;  // Y = postponed, N = normal
}

export interface TeamScheduleDay {
  date: string;
  is_playing: boolean;
  is_past: boolean;
}

export interface TeamScheduleInfo {
  team_id: number;
  team_name: string;
  team_abbr: string;
  current_week_games: number;
  current_week_total: number;
  next_week_games: number;
  current_week_dates: TeamScheduleDay[];
  next_week_dates: TeamScheduleDay[];
}

export interface TeamScheduleResponse {
  teams: TeamScheduleInfo[];
  current_week: number;
  next_week: number;
}

export interface RankedPlayer {
  player_id: number;
  player_name: string;
  team_tricode: string | null;
  rank: number;
  stats: PlayerStats | null;
  z_score: number | null;
}

export interface RankedPlayersResponse {
  players: RankedPlayer[];
  total_count: number;
}

export interface GameTypeSettingsResponse {
  settings: Record<string, boolean>;
  descriptions: Record<string, string>;
  categories: Record<string, string[]>;
  defaults: Record<string, boolean>;
}

// Player Performance Insights Types
export interface PlayerInsight {
  type: string;  // "foul_trouble", "limited_minutes", "benched", etc.
  severity: string;  // "info", "warning", "critical"
  message: string;
  details?: Record<string, unknown> | null;
}

export interface QuarterBreakdown {
  quarter: number;
  quarter_label: string;  // "Q1", "Q2", "Q3", "Q4", "OT1", etc.
  minutes: number;
  points: number;
  fouls: number;
  field_goals_made: number;
  field_goals_attempted: number;
  three_pointers_made: number;
  three_pointers_attempted: number;
  free_throws_made: number;
  free_throws_attempted: number;
  rebounds: number;
  assists: number;
  steals: number;
  blocks: number;
  turnovers: number;
}

export interface FoulEvent {
  quarter: number;
  time_remaining: string;  // "10:30" format
  foul_number: number;
  foul_type: string;  // "personal", "offensive", "technical", etc.
  elapsed_minutes: number;
}

export interface SubstitutionEvent {
  quarter: number;
  time_remaining: string;
  event_type: string;  // "in" or "out"
  elapsed_minutes: number;
}

export interface PlayerInsightsResponse {
  player_id: number;
  player_name: string;
  game_id: string;
  total_minutes: number;
  insights: PlayerInsight[];
  quarter_breakdown: QuarterBreakdown[];
  foul_timeline: FoulEvent[];
  substitution_timeline: SubstitutionEvent[];
}

