/**
 * Waiver Wire Context - Persists waiver wire state across navigation
 */

import { createContext, useContext, useState, ReactNode } from 'react';
import type { WaiverResponse, TeamScheduleResponse } from '../types/api';

type SortField = 'index' | 'rank' | 'name' | 'status' | 'injury' | 'lastGame' | 'games' | 'aggGames' | 'trend' | 'minutes' | 
  'fga' | 'fgm' | 'fg_pct' | 'fta' | 'ftm' | 'ft_pct' | 'threes' | 'points' | 'rebounds' | 'assists' | 'steals' | 'blocks' | 'turnovers' | 'usage_pct';
type SortDirection = 'asc' | 'desc';

interface TeamScheduleCache {
  data: TeamScheduleResponse;
  timestamp: number;
}

interface WaiverWireState {
  // Search parameters
  count: number;
  lookback: string;
  aggMode: string;
  sortField: SortField;
  sortDirection: SortDirection;
  
  // Client-side filters
  lastGameCutoff: string | null; // ISO date string, null means no filter
  
  // Results
  waiverData: WaiverResponse | null;
  
  // Team schedule cache (keyed by league_key)
  teamScheduleCache: Record<string, TeamScheduleCache>;
  
  // UI state
  error: string | null;
}

interface WaiverWireContextType {
  state: WaiverWireState;
  updateState: (updates: Partial<WaiverWireState>) => void;
  clearData: () => void;
  getTeamSchedule: (leagueKey: string) => TeamScheduleResponse | null;
  setTeamSchedule: (leagueKey: string, data: TeamScheduleResponse) => void;
  isTeamScheduleStale: (leagueKey: string, maxAgeMinutes?: number) => boolean;
}

const WaiverWireContext = createContext<WaiverWireContextType | undefined>(undefined);

// Helper to get date N days ago in ISO format
const getDateDaysAgo = (days: number): string => {
  const date = new Date();
  date.setDate(date.getDate() - days);
  return date.toISOString().split('T')[0];
};

const defaultState: WaiverWireState = {
  count: 50,
  lookback: 'last',
  aggMode: 'avg',
  sortField: 'minutes',
  sortDirection: 'desc',
  lastGameCutoff: getDateDaysAgo(7), // Default to 7 days ago
  waiverData: null,
  teamScheduleCache: {},
  error: null,
};

export function WaiverWireProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<WaiverWireState>(defaultState);

  const updateState = (updates: Partial<WaiverWireState>) => {
    setState(prev => ({ ...prev, ...updates }));
  };

  const clearData = () => {
    setState(defaultState);
  };

  const getTeamSchedule = (leagueKey: string): TeamScheduleResponse | null => {
    const cached = state.teamScheduleCache[leagueKey];
    return cached ? cached.data : null;
  };

  const setTeamSchedule = (leagueKey: string, data: TeamScheduleResponse) => {
    setState(prev => ({
      ...prev,
      teamScheduleCache: {
        ...prev.teamScheduleCache,
        [leagueKey]: {
          data,
          timestamp: Date.now(),
        },
      },
    }));
  };

  const isTeamScheduleStale = (leagueKey: string, maxAgeMinutes: number = 60): boolean => {
    const cached = state.teamScheduleCache[leagueKey];
    if (!cached) return true;
    
    const ageMinutes = (Date.now() - cached.timestamp) / (1000 * 60);
    return ageMinutes > maxAgeMinutes;
  };

  return (
    <WaiverWireContext.Provider value={{ 
      state, 
      updateState, 
      clearData, 
      getTeamSchedule, 
      setTeamSchedule, 
      isTeamScheduleStale 
    }}>
      {children}
    </WaiverWireContext.Provider>
  );
}

export function useWaiverWire() {
  const context = useContext(WaiverWireContext);
  if (context === undefined) {
    throw new Error('useWaiverWire must be used within a WaiverWireProvider');
  }
  return context;
}

