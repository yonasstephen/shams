/**
 * Tests for LeagueSelector component
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { LeagueSelector } from '../components/LeagueSelector';
import { LeagueProvider } from '../context/LeagueContext';
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

describe('LeagueSelector', () => {
  const mockLeagues = [
    { league_key: 'nba.l.12345', name: 'Test League 1', league_id: '12345', season: '2024', game_code: 'nba' },
    { league_key: 'nba.l.67890', name: 'Test League 2', league_id: '67890', season: '2024', game_code: 'nba' },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should render loading state', () => {
    (api.getUserLeagues as any).mockImplementation(() => new Promise(() => {}));
    (api.getDefaultLeague as any).mockImplementation(() => new Promise(() => {}));

    render(
      <LeagueProvider>
        <LeagueSelector />
      </LeagueProvider>
    );

    // Should show loading skeleton
    expect(document.querySelector('.animate-pulse')).toBeInTheDocument();
  });

  it('should render league dropdown when leagues are loaded', async () => {
    (api.getUserLeagues as any).mockResolvedValue({ leagues: mockLeagues });
    (api.getDefaultLeague as any).mockResolvedValue({ league_key: null });

    render(
      <LeagueProvider>
        <LeagueSelector />
      </LeagueProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Select League...')).toBeInTheDocument();
    });
  });

  it('should display default league when set', async () => {
    (api.getUserLeagues as any).mockResolvedValue({ leagues: mockLeagues });
    (api.getDefaultLeague as any).mockResolvedValue({ league_key: 'nba.l.12345' });

    render(
      <LeagueProvider>
        <LeagueSelector />
      </LeagueProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Test League 1')).toBeInTheDocument();
    });
  });

  it('should call setDefaultLeague when league is changed', async () => {
    const user = userEvent.setup();
    
    (api.getUserLeagues as any).mockResolvedValue({ leagues: mockLeagues });
    (api.getDefaultLeague as any).mockResolvedValue({ league_key: 'nba.l.12345' });
    (api.setDefaultLeague as any).mockResolvedValue({ league_key: 'nba.l.67890' });

    render(
      <LeagueProvider>
        <LeagueSelector />
      </LeagueProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Test League 1')).toBeInTheDocument();
    });

    // Click the dropdown button to open it (get by aria-haspopup attribute to distinguish from refresh button)
    const buttons = screen.getAllByRole('button');
    const dropdownButton = buttons.find(btn => btn.getAttribute('aria-haspopup') === 'listbox');
    expect(dropdownButton).toBeDefined();
    await user.click(dropdownButton!);

    // Wait for dropdown to open and click on league option
    await waitFor(() => {
      expect(screen.getByRole('listbox')).toBeInTheDocument();
    });

    const league2Option = screen.getByText('Test League 2');
    await user.click(league2Option);

    await waitFor(() => {
      expect(api.setDefaultLeague).toHaveBeenCalledWith('nba.l.67890');
    });
  });

  it('should show "No leagues found" message when no leagues available', async () => {
    (api.getUserLeagues as any).mockResolvedValue({ leagues: [] });
    (api.getDefaultLeague as any).mockResolvedValue({ league_key: null });

    render(
      <LeagueProvider>
        <LeagueSelector />
      </LeagueProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('No leagues found')).toBeInTheDocument();
    });
  });
});

