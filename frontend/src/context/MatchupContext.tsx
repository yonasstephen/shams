/**
 * Matchup Context - Persists matchup state across navigation
 */

import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import type { MatchupProjectionResponse } from '../types/api';

type ContribSortField = 'name' | 'games' | string; // string for stat IDs
type SortDirection = 'asc' | 'desc';

interface MatchupState {
  // Search parameters
  week: number | undefined;
  projectionMode: string;
  optimizeUserRoster: boolean;
  optimizeOpponentRoster: boolean;
  
  // Results
  matchupData: MatchupProjectionResponse | null;
  
  // UI state - Layout
  isMatchupListCollapsed: boolean;
  
  // UI state - Current Contributions sort
  contribSortField: ContribSortField;
  contribSortDirection: SortDirection;
  opponentContribSortField: ContribSortField;
  opponentContribSortDirection: SortDirection;
  
  // UI state - Projection sort
  projectionSortField: ContribSortField;
  projectionSortDirection: SortDirection;
  opponentProjectionSortField: ContribSortField;
  opponentProjectionSortDirection: SortDirection;
  
  error: string | null;
}

interface MatchupContextType {
  state: MatchupState;
  updateState: (updates: Partial<MatchupState>) => void;
  clearData: () => void;
}

const MatchupContext = createContext<MatchupContextType | undefined>(undefined);

const STORAGE_KEY = 'shams_matchup_preferences';

// Settings to persist in localStorage
interface PersistedSettings {
  projectionMode: string;
  optimizeUserRoster: boolean;
  optimizeOpponentRoster: boolean;
  isMatchupListCollapsed: boolean;
}

const defaultState: MatchupState = {
  week: undefined,
  projectionMode: 'season',
  optimizeUserRoster: false,
  optimizeOpponentRoster: false,
  matchupData: null,
  isMatchupListCollapsed: false,
  contribSortField: 'name',
  contribSortDirection: 'asc',
  opponentContribSortField: 'name',
  opponentContribSortDirection: 'asc',
  projectionSortField: 'name',
  projectionSortDirection: 'asc',
  opponentProjectionSortField: 'name',
  opponentProjectionSortDirection: 'asc',
  error: null,
};

function loadPersistedSettings(): Partial<PersistedSettings> {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      return JSON.parse(stored);
    }
  } catch (error) {
    console.warn('Failed to load matchup preferences from localStorage:', error);
  }
  return {};
}

function savePersistedSettings(settings: Partial<PersistedSettings>) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
  } catch (error) {
    console.warn('Failed to save matchup preferences to localStorage:', error);
  }
}

export function MatchupProvider({ children }: { children: ReactNode }) {
  // Load persisted settings on mount
  const [state, setState] = useState<MatchupState>(() => {
    const persisted = loadPersistedSettings();
    return {
      ...defaultState,
      ...persisted,
    };
  });

  // Persist settings whenever they change
  useEffect(() => {
    const settingsToPersist: PersistedSettings = {
      projectionMode: state.projectionMode,
      optimizeUserRoster: state.optimizeUserRoster,
      optimizeOpponentRoster: state.optimizeOpponentRoster,
      isMatchupListCollapsed: state.isMatchupListCollapsed,
    };
    savePersistedSettings(settingsToPersist);
  }, [
    state.projectionMode,
    state.optimizeUserRoster,
    state.optimizeOpponentRoster,
    state.isMatchupListCollapsed,
  ]);

  const updateState = (updates: Partial<MatchupState>) => {
    setState(prev => ({ ...prev, ...updates }));
  };

  const clearData = () => {
    setState((prev: MatchupState) => ({
      ...defaultState,
      // Keep persisted settings even when clearing data
      projectionMode: prev.projectionMode,
      optimizeUserRoster: prev.optimizeUserRoster,
      optimizeOpponentRoster: prev.optimizeOpponentRoster,
      isMatchupListCollapsed: prev.isMatchupListCollapsed,
    }));
  };

  return (
    <MatchupContext.Provider value={{ state, updateState, clearData }}>
      {children}
    </MatchupContext.Provider>
  );
}

export function useMatchup() {
  const context = useContext(MatchupContext);
  if (context === undefined) {
    throw new Error('useMatchup must be used within a MatchupProvider');
  }
  return context;
}

