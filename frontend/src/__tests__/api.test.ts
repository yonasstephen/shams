/**
 * Tests for API client
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { api } from '../services/api';

// Mock axios with factory so create() is available when api.ts module is loaded
vi.mock('axios', () => ({
  default: {
    create: vi.fn(() => ({
      get: vi.fn(),
      post: vi.fn(),
      delete: vi.fn(),
      interceptors: { response: { use: vi.fn() } },
    })),
  },
}));

describe('API Client', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Config endpoints', () => {
    it('should have getDefaultLeague method', () => {
      expect(api.getDefaultLeague).toBeDefined();
      expect(typeof api.getDefaultLeague).toBe('function');
    });

    it('should have setDefaultLeague method', () => {
      expect(api.setDefaultLeague).toBeDefined();
      expect(typeof api.setDefaultLeague).toBe('function');
    });

    it('should have clearDefaultLeague method', () => {
      expect(api.clearDefaultLeague).toBeDefined();
      expect(typeof api.clearDefaultLeague).toBe('function');
    });
  });

  describe('Auth endpoints', () => {
    it('should have getAuthUrl method', () => {
      expect(api.getAuthUrl).toBeDefined();
      expect(typeof api.getAuthUrl).toBe('function');
    });

    it('should have getUserLeagues method', () => {
      expect(api.getUserLeagues).toBeDefined();
      expect(typeof api.getUserLeagues).toBe('function');
    });
  });

  describe('Player endpoints', () => {
    it('should have searchPlayers method', () => {
      expect(api.searchPlayers).toBeDefined();
      expect(typeof api.searchPlayers).toBe('function');
    });

    it('should have getPlayerStats method', () => {
      expect(api.getPlayerStats).toBeDefined();
      expect(typeof api.getPlayerStats).toBe('function');
    });
  });

  describe('Waiver endpoints', () => {
    it('should have getWaiverPlayers method', () => {
      expect(api.getWaiverPlayers).toBeDefined();
      expect(typeof api.getWaiverPlayers).toBe('function');
    });

    it('should have refreshWaiverCache method', () => {
      expect(api.refreshWaiverCache).toBeDefined();
      expect(typeof api.refreshWaiverCache).toBe('function');
    });
  });

  describe('Matchup endpoints', () => {
    it('should have getMatchupProjection method', () => {
      expect(api.getMatchupProjection).toBeDefined();
      expect(typeof api.getMatchupProjection).toBe('function');
    });

    it('should have getAllMatchups method', () => {
      expect(api.getAllMatchups).toBeDefined();
      expect(typeof api.getAllMatchups).toBe('function');
    });
  });
});

