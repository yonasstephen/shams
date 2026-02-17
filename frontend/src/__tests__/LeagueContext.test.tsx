/**
 * Tests for LeagueContext
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { LeagueProvider, useLeague } from '../context/LeagueContext';
import { api } from '../services/api';

// Mock the API
vi.mock('../services/api', () => ({
  api: {
    initSession: vi.fn().mockResolvedValue({}),
    getUserLeagues: vi.fn(),
    getDefaultLeague: vi.fn(),
    setDefaultLeague: vi.fn(),
    getLeagueSettings: vi.fn().mockResolvedValue({ current_week: 1, total_weeks: 22 }),
  },
}));

describe('LeagueContext', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should provide league context', () => {
    const mockLeagues = [
      { league_key: 'nba.l.12345', name: 'Test League 1', league_id: '12345', season: '2024', game_code: 'nba' },
      { league_key: 'nba.l.67890', name: 'Test League 2', league_id: '67890', season: '2024', game_code: 'nba' },
    ];

    (api.getUserLeagues as any).mockResolvedValue({ leagues: mockLeagues });
    (api.getDefaultLeague as any).mockResolvedValue({ league_key: null });

    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <LeagueProvider>{children}</LeagueProvider>
    );

    const { result } = renderHook(() => useLeague(), { wrapper });

    expect(result.current).toBeDefined();
    expect(result.current.leagues).toBeDefined();
    expect(result.current.defaultLeagueKey).toBeDefined();
    expect(result.current.isLoading).toBeDefined();
    expect(result.current.setDefaultLeague).toBeDefined();
    expect(result.current.refreshLeagues).toBeDefined();
  });

  it('should load leagues on mount', async () => {
    const mockLeagues = [
      { league_key: 'nba.l.12345', name: 'Test League 1', league_id: '12345', season: '2024', game_code: 'nba' },
    ];

    (api.getUserLeagues as any).mockResolvedValue({ leagues: mockLeagues });
    (api.getDefaultLeague as any).mockResolvedValue({ league_key: null });

    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <LeagueProvider>{children}</LeagueProvider>
    );

    const { result } = renderHook(() => useLeague(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(api.getUserLeagues).toHaveBeenCalled();
    expect(api.getDefaultLeague).toHaveBeenCalled();
  });

  it('should set default league', async () => {
    const mockLeagues = [
      { league_key: 'nba.l.12345', name: 'Test League 1', league_id: '12345', season: '2024', game_code: 'nba' },
    ];

    (api.getUserLeagues as any).mockResolvedValue({ leagues: mockLeagues });
    (api.getDefaultLeague as any).mockResolvedValue({ league_key: null });
    (api.setDefaultLeague as any).mockResolvedValue({ league_key: 'nba.l.12345' });

    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <LeagueProvider>{children}</LeagueProvider>
    );

    const { result } = renderHook(() => useLeague(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    await result.current.setDefaultLeague('nba.l.12345');

    expect(api.setDefaultLeague).toHaveBeenCalledWith('nba.l.12345');
    await waitFor(() => {
      expect(result.current.defaultLeagueKey).toBe('nba.l.12345');
    });
  });

  it('should throw error when used outside provider', () => {
    expect(() => {
      renderHook(() => useLeague());
    }).toThrow('useLeague must be used within a LeagueProvider');
  });
});

