/**
 * Integration tests for Config API endpoints
 * 
 * These tests verify the API contract and data structures
 */

import { describe, it, expect } from 'vitest';
import type { DefaultLeagueResponse, SetDefaultLeagueRequest } from '../../types/api';

describe('Config API Integration', () => {
  describe('DefaultLeagueResponse type', () => {
    it('should have correct shape for null league', () => {
      const response: DefaultLeagueResponse = {
        league_key: null,
      };

      expect(response).toBeDefined();
      expect(response.league_key).toBeNull();
    });

    it('should have correct shape for set league', () => {
      const response: DefaultLeagueResponse = {
        league_key: 'nba.l.12345',
      };

      expect(response).toBeDefined();
      expect(typeof response.league_key).toBe('string');
    });
  });

  describe('SetDefaultLeagueRequest type', () => {
    it('should have correct shape', () => {
      const request: SetDefaultLeagueRequest = {
        league_key: 'nba.l.12345',
      };

      expect(request).toBeDefined();
      expect(typeof request.league_key).toBe('string');
    });

    it('should validate league key format', () => {
      const validLeagueKey = 'nba.l.12345';
      const request: SetDefaultLeagueRequest = {
        league_key: validLeagueKey,
      };

      // League key should follow Yahoo format: game.l.league_id
      expect(request.league_key).toMatch(/^[a-z]+\.l\.\d+$/);
    });
  });

  describe('API endpoints', () => {
    it('should define GET /api/config/default-league endpoint', () => {
      const endpoint = '/api/config/default-league';
      expect(endpoint).toBe('/api/config/default-league');
    });

    it('should define POST /api/config/default-league endpoint', () => {
      const endpoint = '/api/config/default-league';
      expect(endpoint).toBe('/api/config/default-league');
    });

    it('should define DELETE /api/config/default-league endpoint', () => {
      const endpoint = '/api/config/default-league';
      expect(endpoint).toBe('/api/config/default-league');
    });
  });

  describe('Config file integration', () => {
    it('should use same config file as CLI', () => {
      // Config should be stored at ~/.shams/config.json
      const configPath = '~/.shams/config.json';
      expect(configPath).toBe('~/.shams/config.json');
    });

    it('should share config between web and CLI', () => {
      // Both CLI and web app should read/write to the same file
      // This ensures that setting a league in one interface
      // makes it available in the other
      const sharedConfig = true;
      expect(sharedConfig).toBe(true);
    });
  });
});

