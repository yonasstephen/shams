/**
 * League Context - Manages league state and selection
 */

import { createContext, useContext, useState, useEffect, ReactNode, useCallback } from 'react';
import { api } from '../services/api';
import type { LeagueInfo } from '../types/api';

interface LeagueContextType {
  leagues: LeagueInfo[];
  defaultLeagueKey: string | null;
  currentWeek: number | undefined;
  totalWeeks: number | undefined;
  isLoading: boolean;
  error: string | null;
  setDefaultLeague: (leagueKey: string) => Promise<void>;
  refreshLeagues: () => Promise<void>;
}

const LeagueContext = createContext<LeagueContextType | undefined>(undefined);

export function LeagueProvider({ children }: { children: ReactNode }) {
  const [leagues, setLeagues] = useState<LeagueInfo[]>([]);
  const [defaultLeagueKey, setDefaultLeagueKey] = useState<string | null>(null);
  const [currentWeek, setCurrentWeek] = useState<number | undefined>(undefined);
  const [totalWeeks, setTotalWeeks] = useState<number | undefined>(undefined);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadLeagues = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);
      
      // Try to restore session from existing tokens first
      try {
        await api.initSession();
      } catch (initErr) {
        console.log('No existing session to restore, will need to login');
      }
      
      // Fetch both leagues and default league in parallel
      const [leaguesResponse, defaultResponse] = await Promise.all([
        api.getUserLeagues(),
        api.getDefaultLeague(),
      ]);
      
      setLeagues(leaguesResponse.leagues || []);
      setDefaultLeagueKey(defaultResponse.league_key);
      
      // If there's a default league, fetch its settings
      if (defaultResponse.league_key) {
        try {
          const settings = await api.getLeagueSettings(defaultResponse.league_key);
          setCurrentWeek(settings.current_week);
          setTotalWeeks(settings.total_weeks);
        } catch (settingsErr) {
          console.error('Failed to load league settings:', settingsErr);
          // Don't fail the entire load if settings fail
        }
      }
    } catch (err: any) {
      console.error('Failed to load leagues:', err);
      setError(err.message || 'Failed to load leagues');
    } finally {
      setIsLoading(false);
    }
  }, []);

  const refreshLeagues = useCallback(async () => {
    await loadLeagues();
  }, [loadLeagues]);

  const handleSetDefaultLeague = useCallback(async (leagueKey: string) => {
    try {
      await api.setDefaultLeague(leagueKey);
      setDefaultLeagueKey(leagueKey);
      
      // Fetch league settings for the new default league
      try {
        const settings = await api.getLeagueSettings(leagueKey);
        setCurrentWeek(settings.current_week);
        setTotalWeeks(settings.total_weeks);
      } catch (settingsErr) {
        console.error('Failed to load league settings:', settingsErr);
        // Don't fail if settings fail
      }
    } catch (err: any) {
      console.error('Failed to set default league:', err);
      throw err;
    }
  }, []);

  // Load leagues on mount
  useEffect(() => {
    loadLeagues();
  }, [loadLeagues]);

  return (
    <LeagueContext.Provider
      value={{
        leagues,
        defaultLeagueKey,
        currentWeek,
        totalWeeks,
        isLoading,
        error,
        setDefaultLeague: handleSetDefaultLeague,
        refreshLeagues,
      }}
    >
      {children}
    </LeagueContext.Provider>
  );
}

export function useLeague() {
  const context = useContext(LeagueContext);
  if (context === undefined) {
    throw new Error('useLeague must be used within a LeagueProvider');
  }
  return context;
}


