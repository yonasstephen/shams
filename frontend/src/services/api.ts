/**
 * API client for Shams backend
 */

import axios, { AxiosInstance } from 'axios';
import type {
  PlayerSearchResponse,
  PlayerStatsResponse,
  WaiverResponse,
  MatchupProjectionResponse,
  AllMatchupsResponse,
  UserResponse,
  DefaultLeagueResponse,
  SetDefaultLeagueRequest,
  LeagueSettingsResponse,
  CacheDebugResponse,
  BoxScoreDate,
  LatestDateResponse,
  GameBoxScore,
  TeamScheduleResponse,
  RankedPlayersResponse,
  GameTypeSettingsResponse,
  PlayerInsightsResponse,
} from '../types/api';

// Get API URL from runtime config (set at container startup) or build-time env var
// In Docker production, __API_URL__ placeholder is replaced at container startup
// In local dev, the placeholder won't be replaced so we fall back to env var or default
const configUrl = window.APP_CONFIG?.API_URL;
const isPlaceholder = !configUrl || configUrl === '__API_URL__';
const API_BASE_URL = isPlaceholder 
  ? (import.meta.env.VITE_API_URL || 'https://localhost:8000')
  : configUrl;

class ApiClient {
  private client: AxiosInstance;

  constructor() {
    this.client = axios.create({
      baseURL: API_BASE_URL,
      withCredentials: true, // Important for cookies
      headers: {
        'Content-Type': 'application/json',
      },
    });

    // Response interceptor for error handling
    this.client.interceptors.response.use(
      (response) => response,
      (error) => {
        if (error.response?.status === 401) {
          // Redirect to login on auth error (but only if not already on login page)
          if (!window.location.pathname.startsWith('/login') && 
              !window.location.pathname.startsWith('/auth/')) {
            window.location.href = '/login';
          }
        }
        return Promise.reject(error);
      }
    );
  }

  // Auth endpoints
  async initSession(): Promise<{ authenticated: boolean; message: string }> {
    const response = await this.client.get('/api/auth/init');
    return response.data;
  }

  async getAuthUrl(): Promise<{ auth_url: string; state: string }> {
    const response = await this.client.get('/api/auth/login');
    return response.data;
  }

  async logout(): Promise<void> {
    await this.client.post('/api/auth/logout');
  }

  async getCurrentUser(): Promise<UserResponse> {
    const response = await this.client.get('/api/auth/me');
    return response.data;
  }

  async getUserLeagues(): Promise<{ leagues: any[] }> {
    const response = await this.client.get('/api/auth/leagues');
    return response.data;
  }

  // Player endpoints
  async searchPlayers(name: string, seasonType = 'Regular Season'): Promise<PlayerSearchResponse> {
    const response = await this.client.get('/api/players/search', {
      params: { name, season_type: seasonType },
    });
    return response.data;
  }

  async getPlayerStats(playerId: number, seasonType = 'Regular Season', leagueKey?: string): Promise<PlayerStatsResponse> {
    const response = await this.client.get(`/api/players/${playerId}`, {
      params: { 
        season_type: seasonType,
        league_key: leagueKey,
      },
    });
    return response.data;
  }

  async getRankedPlayers(
    leagueKey: string,
    options?: {
      maxRank?: number;
      statsMode?: string;
      aggMode?: string;
      rankingMode?: 'yahoo' | '9cat';
    }
  ): Promise<RankedPlayersResponse> {
    const response = await this.client.get('/api/players/ranked', {
      params: {
        league_key: leagueKey,
        max_rank: options?.maxRank || 150,
        stats_mode: options?.statsMode || 'season',
        agg_mode: options?.aggMode || 'avg',
        ranking_mode: options?.rankingMode || 'yahoo',
      },
    });
    return response.data;
  }

  // Waiver endpoints
  async getWaiverPlayers(
    leagueKey: string,
    options?: {
      count?: number;
      statsMode?: string;
      aggMode?: string;
      sortColumn?: string;
      sortAscending?: boolean;
      refresh?: boolean;
    }
  ): Promise<WaiverResponse> {
    const response = await this.client.get('/api/waiver', {
      params: {
        league_key: leagueKey,
        count: options?.count || 50,
        stats_mode: options?.statsMode || 'last',
        agg_mode: options?.aggMode || 'avg',
        sort_column: options?.sortColumn,
        sort_ascending: options?.sortAscending,
        refresh: options?.refresh || false,
      },
    });
    return response.data;
  }

  async refreshWaiverCache(leagueKey: string): Promise<{ message: string; player_count: number }> {
    const response = await this.client.post('/api/waiver/refresh', null, {
      params: { league_key: leagueKey },
    });
    return response.data;
  }

  // Matchup endpoints
  async getMatchupProjection(
    leagueKey: string, 
    week?: number,
    projectionMode: string = 'season',
    teamKey?: string,
    optimizeUserRoster: boolean = false,
    optimizeOpponentRoster: boolean = false
  ): Promise<MatchupProjectionResponse> {
    const response = await this.client.get('/api/matchup', {
      params: {
        league_key: leagueKey,
        week,
        projection_mode: projectionMode,
        team_key: teamKey,
        optimize_user_roster: optimizeUserRoster,
        optimize_opponent_roster: optimizeOpponentRoster,
      },
    });
    return response.data;
  }

  async getAllMatchups(
    leagueKey: string, 
    week?: number,
    projectionMode: string = 'season'
  ): Promise<AllMatchupsResponse> {
    const response = await this.client.get('/api/matchup/all', {
      params: {
        league_key: leagueKey,
        week,
        projection_mode: projectionMode,
      },
    });
    return response.data;
  }

  // Config endpoints
  async getDefaultLeague(): Promise<DefaultLeagueResponse> {
    const response = await this.client.get('/api/config/default-league');
    return response.data;
  }

  async setDefaultLeague(leagueKey: string): Promise<DefaultLeagueResponse> {
    const response = await this.client.post('/api/config/default-league', {
      league_key: leagueKey,
    } as SetDefaultLeagueRequest);
    return response.data;
  }

  async clearDefaultLeague(): Promise<{ message: string }> {
    const response = await this.client.delete('/api/config/default-league');
    return response.data;
  }

  // League endpoints
  async getLeagueSettings(leagueKey: string): Promise<LeagueSettingsResponse> {
    const response = await this.client.get(`/api/league/${leagueKey}/settings`);
    return response.data;
  }

  async getTeamSchedule(leagueKey: string): Promise<TeamScheduleResponse> {
    const response = await this.client.get(`/api/league/${leagueKey}/team-schedule`);
    return response.data;
  }

  // Cache debug endpoint
  async getCacheDebugData(): Promise<CacheDebugResponse> {
    const response = await this.client.get('/api/config/cache-debug');
    return response.data;
  }

  // Box score endpoints
  async getBoxScoreDates(): Promise<BoxScoreDate[]> {
    const response = await this.client.get('/api/boxscore/dates');
    return response.data;
  }

  async getLatestBoxScoreDate(): Promise<LatestDateResponse> {
    const response = await this.client.get('/api/boxscore/latest-date');
    return response.data;
  }

  async getGamesForDate(date: string): Promise<GameBoxScore[]> {
    const response = await this.client.get(`/api/boxscore/games/${date}`);
    return response.data;
  }

  async getPlayerInsights(gameId: string, playerId: number): Promise<PlayerInsightsResponse> {
    const response = await this.client.get(`/api/boxscore/player-insights/${gameId}/${playerId}`);
    return response.data;
  }

  // Game type settings endpoints
  async getGameTypeSettings(): Promise<GameTypeSettingsResponse> {
    const response = await this.client.get('/api/config/game-type-settings');
    return response.data;
  }

  async updateGameTypeSettings(settings: Record<string, boolean>): Promise<GameTypeSettingsResponse> {
    const response = await this.client.post('/api/config/game-type-settings', {
      settings,
    });
    return response.data;
  }
}

export const api = new ApiClient();

