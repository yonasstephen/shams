/**
 * Waiver wire page
 */

import { useState, useEffect, useCallback } from 'react';
import { Layout } from '../components/Layout';
import { StatCell } from '../components/StatCell';
import { PlayerStatsModal } from '../components/PlayerStatsModal';
import { Dropdown } from '../components/Dropdown';
import { TeamScheduleCard } from '../components/TeamScheduleCard';
import { api } from '../services/api';
import { useLeague } from '../context/LeagueContext';
import { useWaiverWire } from '../context/WaiverWireContext';
import type { WaiverPlayer, LeagueInfo, TeamScheduleResponse } from '../types/api';
import { getTrendColor, getColorClass } from '../utils/statColors';

type SortField = 'index' | 'rank' | 'name' | 'status' | 'injury' | 'lastGame' | 'games' | 'aggGames' | 'trend' | 'minutes' | 
  'fga' | 'fgm' | 'fg_pct' | 'fta' | 'ftm' | 'ft_pct' | 'threes' | 'points' | 'rebounds' | 'assists' | 'steals' | 'blocks' | 'turnovers' | 'usage_pct';
type SortDirection = 'asc' | 'desc';

export function WaiverWire() {
  const { leagues, defaultLeagueKey } = useLeague();
  const { state, updateState, getTeamSchedule, setTeamSchedule: cacheTeamSchedule, isTeamScheduleStale } = useWaiverWire();
  const [leagueKey, setLeagueKey] = useState('');
  const [loading, setLoading] = useState(false);
  const [selectedPlayer, setSelectedPlayer] = useState<{ id: number | null; name: string } | null>(null);
  const [hasAutoFetched, setHasAutoFetched] = useState(false);
  const [teamSchedule, setTeamSchedule] = useState<TeamScheduleResponse | null>(null);
  const [scheduleLoading, setScheduleLoading] = useState(false);
  const [scheduleCollapsed, setScheduleCollapsed] = useState(false);
  
  // Memoize the collapse handler to prevent unnecessary re-renders of TeamScheduleCard
  const handleCollapseSchedule = useCallback(() => setScheduleCollapsed(true), []);
  
  // Destructure state from context
  const { count, lookback, aggMode, waiverData, error, sortField, sortDirection, lastGameCutoff } = state;
  
  // Compute default cutoff (7 days ago) if not set
  const getDefaultCutoff = () => {
    const date = new Date();
    date.setDate(date.getDate() - 7);
    return date.toISOString().split('T')[0];
  };
  
  const effectiveCutoff = lastGameCutoff ?? getDefaultCutoff();
  
  // Filter players by last game cutoff (client-side filtering)
  const filteredPlayers = waiverData?.players.filter(player => {
    if (!effectiveCutoff) return true; // No filter (null means explicitly cleared)
    if (!player.last_game_date) return false; // No last game date means hasn't played
    return player.last_game_date >= effectiveCutoff;
  }) ?? [];

  useEffect(() => {
    // Use default league key from context
    if (defaultLeagueKey) {
      setLeagueKey(defaultLeagueKey);
    } else if (leagues.length > 0) {
      setLeagueKey(leagues[0].league_key);
    }
  }, [defaultLeagueKey, leagues]);

  // Fetch team schedule when league key is set (with caching)
  useEffect(() => {
    const fetchTeamSchedule = async () => {
      if (!leagueKey) return;
      
      // Check if we have a cached version that's not stale
      const cached = getTeamSchedule(leagueKey);
      if (cached && !isTeamScheduleStale(leagueKey, 60)) {
        // Use cached data if it's less than 60 minutes old
        setTeamSchedule(cached);
        return;
      }
      
      // Fetch fresh data if cache is missing or stale
      setScheduleLoading(true);
      try {
        const data = await api.getTeamSchedule(leagueKey);
        setTeamSchedule(data);
        cacheTeamSchedule(leagueKey, data);
      } catch (err) {
        console.error('Failed to fetch team schedule:', err);
        // Don't show error to user, just fail silently
        // If we have stale cache, use it as fallback
        if (cached) {
          setTeamSchedule(cached);
        }
      } finally {
        setScheduleLoading(false);
      }
    };

    fetchTeamSchedule();
  }, [leagueKey, getTeamSchedule, isTeamScheduleStale, cacheTeamSchedule]);

  // Map frontend sort fields to backend column names
  const mapSortFieldToColumn = (field: SortField): string | undefined => {
    const mapping: Record<SortField, string | undefined> = {
      'index': undefined,
      'rank': undefined, // Frontend-only sorting by rank
      'name': undefined, // Backend doesn't support name sorting
      'status': undefined, // Backend doesn't support status sorting
      'injury': undefined, // Backend doesn't support injury sorting
      'lastGame': undefined, // Backend doesn't support last game sorting
      'games': undefined, // Backend doesn't support games sorting
      'aggGames': undefined, // Backend doesn't support agg games sorting
      'trend': 'TREND',
      'minutes': 'MIN',
      'fga': 'FGA',
      'fgm': 'FGM',
      'fg_pct': 'FG%',
      'fta': 'FTA',
      'ftm': 'FTM',
      'ft_pct': 'FT%',
      'threes': '3PM',
      'points': 'PTS',
      'rebounds': 'REB',
      'assists': 'AST',
      'steals': 'STL',
      'blocks': 'BLK',
      'turnovers': 'TO',
      'usage_pct': 'USG%',
    };
    return mapping[field];
  };

  const handleFetch = useCallback(async () => {
    if (!leagueKey.trim()) {
      updateState({ error: 'Please enter a league key' });
      return;
    }

    setLoading(true);
    updateState({ error: null });

    try {
      const sortColumn = mapSortFieldToColumn(sortField);
      const data = await api.getWaiverPlayers(leagueKey.trim(), {
        count,
        statsMode: lookback,
        aggMode: aggMode,
        sortColumn,
        sortAscending: sortDirection === 'asc',
        refresh: true, // Always fetch fresh data from Yahoo
      });
      updateState({ waiverData: data, error: null });
    } catch (err: any) {
      let errorMessage = 'Failed to fetch waiver players. Please try again.';
      if (err.response?.status === 401) {
        errorMessage = 'Authentication required. Please log in again.';
      } else if (err.response?.status === 500) {
        errorMessage = err.response?.data?.detail || 'Server error. Please try again later.';
      } else if (!navigator.onLine) {
        errorMessage = 'Network error. Please check your connection.';
      } else if (err.response?.data?.detail) {
        errorMessage = err.response.data.detail;
      }
      updateState({ error: errorMessage });
    } finally {
      setLoading(false);
    }
  }, [leagueKey, count, lookback, aggMode, sortField, sortDirection, updateState]);

  // Auto-fetch players on first load if no data exists
  useEffect(() => {
    if (leagueKey && !hasAutoFetched) {
      // Only auto-fetch if there's no waiver data
      const needsFetch = !waiverData;
      if (needsFetch) {
        setHasAutoFetched(true);
        handleFetch();
      }
    }
  }, [leagueKey, hasAutoFetched, waiverData, handleFetch]);

  const handleSort = async (field: SortField) => {
    // For fields not supported by backend, just return (or implement client-side sorting)
    const backendColumn = mapSortFieldToColumn(field);
    if (!backendColumn) {
      // Fields like name, status, injury, etc. aren't supported by backend yet
      // Could implement client-side sorting here if needed
      return;
    }

    let newDirection: SortDirection;
    if (sortField === field) {
      // Toggle direction if clicking the same field
      newDirection = sortDirection === 'asc' ? 'desc' : 'asc';
    } else {
      // New field, default to descending for most stats (higher is better)
      // except for turnovers where lower is better
      newDirection = field === 'turnovers' ? 'asc' : 'desc';
    }

    updateState({ sortField: field, sortDirection: newDirection });

    // Refetch with new sort parameters
    if (!leagueKey.trim()) return;

    setLoading(true);
    updateState({ error: null });

    try {
      const sortColumn = mapSortFieldToColumn(field);
      const data = await api.getWaiverPlayers(leagueKey.trim(), {
        count,
        statsMode: lookback,
        aggMode: aggMode,
        sortColumn,
        sortAscending: newDirection === 'asc',
        refresh: false, // Don't force refresh when sorting
      });
      updateState({ waiverData: data, error: null });
    } catch (err: any) {
      let errorMessage = 'Failed to fetch waiver players. Please try again.';
      if (err.response?.status === 401) {
        errorMessage = 'Authentication required. Please log in again.';
      } else if (err.response?.status === 500) {
        errorMessage = err.response?.data?.detail || 'Server error. Please try again later.';
      } else if (!navigator.onLine) {
        errorMessage = 'Network error. Please check your connection.';
      } else if (err.response?.data?.detail) {
        errorMessage = err.response.data.detail;
      }
      updateState({ error: errorMessage });
    } finally {
      setLoading(false);
    }
  };

  const SortIcon = ({ field }: { field: SortField }) => {
    if (sortField !== field) {
      return <span className="text-gray-400 ml-1">↕</span>;
    }
    return <span className="text-neutral-900 ml-1">{sortDirection === 'asc' ? '↑' : '↓'}</span>;
  };

  return (
    <Layout>
      <div className="px-4 py-4 md:py-6">
        <h1 className="text-2xl md:text-3xl font-bold text-neutral-900 mb-4 md:mb-6">Waiver Wire</h1>

        {/* League requirement warning */}
        {!defaultLeagueKey && (
          <div className="bg-blue-50 border border-blue-200 rounded-xl p-5 mb-6">
            <p className="text-blue-800 font-semibold">No league selected</p>
            <p className="text-blue-700 text-sm mt-1.5">
              Please <a href="/" className="underline font-medium">select a league</a> from the home page first, or enter a league key below.
            </p>
          </div>
        )}

        {/* Team Schedule Cards - Above filters on mobile, right side on desktop */}
        <div className="lg:hidden mb-6">
          {scheduleCollapsed ? (
            <button
              onClick={() => setScheduleCollapsed(false)}
              className="w-full card p-4 hover:bg-neutral-50 transition-colors flex items-center justify-between"
            >
              <div className="flex items-center gap-3">
                <svg className="w-5 h-5 text-neutral-900" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                </svg>
                <span className="font-semibold text-neutral-900">Team Schedules</span>
              </div>
              <svg className="w-5 h-5 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </button>
          ) : (
            <div className="space-y-4">
              {scheduleLoading || !teamSchedule ? (
                <>
                  <TeamScheduleCard
                    teams={[]}
                    weekNumber={0}
                    weekType="current"
                    loading={true}
                    onCollapse={handleCollapseSchedule}
                  />
                  <TeamScheduleCard
                    teams={[]}
                    weekNumber={0}
                    weekType="next"
                    loading={true}
                    onCollapse={handleCollapseSchedule}
                  />
                </>
              ) : (
                <>
                  <TeamScheduleCard
                    teams={teamSchedule.teams}
                    weekNumber={teamSchedule.current_week}
                    weekType="current"
                    loading={false}
                    onCollapse={handleCollapseSchedule}
                  />
                  <TeamScheduleCard
                    teams={teamSchedule.teams}
                    weekNumber={teamSchedule.next_week}
                    weekType="next"
                    loading={false}
                    onCollapse={handleCollapseSchedule}
                  />
                </>
              )}
            </div>
          )}
        </div>

        {/* Main content area with responsive grid */}
        <div className={`lg:grid lg:grid-cols-12 lg:gap-6 ${scheduleCollapsed ? '' : ''}`}>
          {/* Left column - Filters and table */}
          <div className={scheduleCollapsed ? 'lg:col-span-12' : 'lg:col-span-8'}>
            <div className="card p-4 md:p-6 mb-4 md:mb-6">
          {defaultLeagueKey && (
            <div className="mb-4 md:mb-5 text-xs md:text-sm text-gray-700">
              Using league: <span className="font-semibold text-neutral-900">{leagues.find((l: LeagueInfo) => l.league_key === defaultLeagueKey)?.name || defaultLeagueKey}</span>
            </div>
          )}
          <div className="grid grid-cols-2 md:grid-cols-2 lg:grid-cols-4 gap-3 md:gap-4 mb-4 md:mb-5">
            {!defaultLeagueKey && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  League Key
                </label>
                <input
                  type="text"
                  value={leagueKey}
                  onChange={(e) => setLeagueKey(e.target.value)}
                  placeholder="Enter league key..."
                  className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-neutral-900 focus:border-transparent transition-all"
                />
              </div>
            )}

            <div>
              <label className="block text-xs md:text-sm font-medium text-gray-700 mb-2">
                Player Count
              </label>
              <Dropdown
                value={count === 9999 ? 'all' : count.toString()}
                onChange={(value) => updateState({ count: value === 'all' ? 9999 : parseInt(String(value)) })}
                options={[
                  { value: '25', label: '25' },
                  { value: '50', label: '50' },
                  { value: '75', label: '75' },
                  { value: '100', label: '100' },
                  { value: '200', label: '200' },
                  { value: 'all', label: 'All' },
                ]}
                className="w-full"
              />
            </div>

            <div>
              <label className="block text-xs md:text-sm font-medium text-gray-700 mb-2">
                Lookback Period
              </label>
              <Dropdown
                value={lookback}
                onChange={(value) => updateState({ lookback: String(value) })}
                options={[
                  { value: 'last', label: 'Last Game' },
                  { value: 'last3', label: 'Last 3' },
                  { value: 'last7', label: 'Last 7' },
                  { value: 'last7d', label: '7 Days' },
                  { value: 'last14d', label: '14 Days' },
                  { value: 'last30d', label: '30 Days' },
                  { value: 'season', label: 'Season' },
                ]}
                className="w-full"
              />
            </div>

            <div className="col-span-2 md:col-span-1">
              <label className="block text-xs md:text-sm font-medium text-gray-700 mb-2">
                Aggregation
              </label>
              <Dropdown
                value={aggMode}
                onChange={(value) => updateState({ aggMode: String(value) })}
                options={[
                  { value: 'avg', label: 'Average' },
                  { value: 'sum', label: 'Sum' },
                ]}
                className="w-full"
              />
            </div>

            <div className="col-span-2 md:col-span-1">
              <label className="block text-xs md:text-sm font-medium text-gray-700 mb-2">
                Last Game After
              </label>
              <div className="relative">
                <input
                  type="date"
                  value={effectiveCutoff || ''}
                  onChange={(e) => updateState({ lastGameCutoff: e.target.value || null })}
                  className="w-full px-3 py-2 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-neutral-900 focus:border-transparent transition-all text-sm"
                />
                {effectiveCutoff && (
                  <button
                    onClick={() => updateState({ lastGameCutoff: null })}
                    className="absolute right-8 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 transition-colors"
                    title="Clear filter"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                )}
              </div>
            </div>

          </div>

          <button
            onClick={() => handleFetch()}
            disabled={loading}
            className="w-full md:w-auto px-6 py-2.5 bg-neutral-900 text-white rounded-xl hover:bg-neutral-850 disabled:opacity-50 disabled:cursor-not-allowed transition-colors font-medium text-sm md:text-base"
          >
            {loading ? 'Loading...' : 'Fetch Players'}
          </button>
            </div>

            {error && (
              <div className="bg-red-50 border border-red-200 rounded-xl p-4 md:p-5 mb-4 md:mb-6">
                <p className="text-red-600 text-sm md:text-base">{error}</p>
              </div>
            )}

            {/* Loading skeleton for first load */}
            {loading && !waiverData && (
              <div className="card overflow-hidden">
                <div className="flex flex-col items-center justify-center py-20">
                  <div className="animate-spin rounded-full h-16 w-16 border-b-2 border-neutral-900 mb-4"></div>
                  <p className="text-neutral-900 font-semibold text-lg">Loading waiver players...</p>
                  <p className="text-gray-600 text-sm mt-2">This may take a moment</p>
                </div>
              </div>
            )}

            {/* Show count of filtered players */}
            {waiverData && waiverData.players.length > 0 && (
              <div className="mb-4 text-sm text-gray-600">
                Showing {filteredPlayers.length} of {waiverData.players.length} players
                {effectiveCutoff && filteredPlayers.length < waiverData.players.length && (
                  <span className="text-gray-500"> (filtered by last game date)</span>
                )}
              </div>
            )}

            {/* Show message when all players filtered out */}
            {waiverData && waiverData.players.length > 0 && filteredPlayers.length === 0 && (
              <div className="card p-8 text-center">
                <p className="text-gray-600 mb-2">No players match the current filter.</p>
                <p className="text-sm text-gray-500">
                  All {waiverData.players.length} players have their last game before {effectiveCutoff}.
                </p>
                <button
                  onClick={() => updateState({ lastGameCutoff: null })}
                  className="mt-4 px-4 py-2 text-sm bg-neutral-100 hover:bg-neutral-200 text-neutral-900 rounded-lg transition-colors"
                >
                  Clear date filter
                </button>
              </div>
            )}

            {waiverData && filteredPlayers.length > 0 && (
          <div className="card overflow-hidden relative">
            {loading && (
              <div className="absolute inset-0 bg-white bg-opacity-75 flex items-center justify-center z-10">
                <div className="flex flex-col items-center">
                  <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-neutral-900"></div>
                  <p className="mt-3 text-neutral-900 font-medium text-sm md:text-base">Loading...</p>
                </div>
              </div>
            )}
            <div className={`overflow-x-auto touch-scroll ${loading ? 'opacity-50' : ''}`}>
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-neutral-50">
                  <tr>
                    <th className="sticky left-0 z-20 w-12 min-w-[3rem] px-2 py-2 text-center text-xs font-semibold text-gray-600 uppercase tracking-wider bg-neutral-50">
                      #
                    </th>
                    <th 
                      className="px-2 py-2 text-center text-xs font-semibold text-gray-600 uppercase tracking-wider cursor-pointer hover:bg-neutral-100 transition-colors select-none"
                      onClick={() => handleSort('rank')}
                      title="Yahoo Fantasy Rank (Actual Rank)"
                    >
                      <div className="flex items-center justify-center">
                        Rank
                        <SortIcon field="rank" />
                      </div>
                    </th>
                    <th 
                      className="sticky left-12 z-20 px-2 py-2 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider cursor-pointer hover:bg-neutral-100 transition-colors select-none bg-neutral-50 shadow-[2px_0_4px_-2px_rgba(0,0,0,0.1)]"
                      onClick={() => handleSort('name')}
                    >
                      <div className="flex items-center">
                        Player
                        <SortIcon field="name" />
                      </div>
                    </th>
                    <th 
                      className="px-2 py-2 text-center text-xs font-semibold text-gray-600 uppercase tracking-wider cursor-pointer hover:bg-neutral-100 transition-colors select-none"
                      onClick={() => handleSort('games')}
                    >
                      <div className="flex items-center justify-center">
                        Games (Week {waiverData.current_week})
                        <SortIcon field="games" />
                      </div>
                    </th>
                    <th 
                      className="px-2 py-2 text-center text-xs font-semibold text-gray-600 uppercase tracking-wider"
                    >
                      <div className="flex items-center justify-center">
                        Games (Week {waiverData.current_week + 1})
                      </div>
                    </th>
                    <th 
                      className="px-2 py-2 text-center text-xs font-semibold text-gray-600 uppercase tracking-wider cursor-pointer hover:bg-neutral-100 transition-colors select-none"
                      onClick={() => handleSort('aggGames')}
                    >
                      <div className="flex items-center justify-center">
                        Agg Games
                        <SortIcon field="aggGames" />
                      </div>
                    </th>
                    <th 
                      className="px-2 py-2 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider cursor-pointer hover:bg-neutral-100 transition-colors select-none"
                      onClick={() => handleSort('trend')}
                    >
                      <div className="flex items-center justify-end">
                        Min Trend
                        <SortIcon field="trend" />
                      </div>
                    </th>
                    <th 
                      className="px-2 py-2 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider cursor-pointer hover:bg-neutral-100 transition-colors select-none"
                      onClick={() => handleSort('minutes')}
                    >
                      <div className="flex items-center justify-end">
                        Minute
                        <SortIcon field="minutes" />
                      </div>
                    </th>
                    <th 
                      className="px-2 py-2 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider cursor-pointer hover:bg-neutral-100 transition-colors select-none"
                      onClick={() => handleSort('fgm')}
                    >
                      <div className="flex items-center justify-end">
                        FGM
                        <SortIcon field="fgm" />
                      </div>
                    </th>
                    <th 
                      className="px-2 py-2 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider cursor-pointer hover:bg-neutral-100 transition-colors select-none"
                      onClick={() => handleSort('fga')}
                    >
                      <div className="flex items-center justify-end">
                        FGA
                        <SortIcon field="fga" />
                      </div>
                    </th>
                    <th 
                      className="px-2 py-2 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider cursor-pointer hover:bg-neutral-100 transition-colors select-none"
                      onClick={() => handleSort('fg_pct')}
                    >
                      <div className="flex items-center justify-end">
                        FG%
                        <SortIcon field="fg_pct" />
                      </div>
                    </th>
                    <th 
                      className="px-2 py-2 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider cursor-pointer hover:bg-neutral-100 transition-colors select-none"
                      onClick={() => handleSort('ftm')}
                    >
                      <div className="flex items-center justify-end">
                        FTM
                        <SortIcon field="ftm" />
                      </div>
                    </th>
                    <th 
                      className="px-2 py-2 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider cursor-pointer hover:bg-neutral-100 transition-colors select-none"
                      onClick={() => handleSort('fta')}
                    >
                      <div className="flex items-center justify-end">
                        FTA
                        <SortIcon field="fta" />
                      </div>
                    </th>
                    <th 
                      className="px-2 py-2 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider cursor-pointer hover:bg-neutral-100 transition-colors select-none"
                      onClick={() => handleSort('ft_pct')}
                    >
                      <div className="flex items-center justify-end">
                        FT%
                        <SortIcon field="ft_pct" />
                      </div>
                    </th>
                    <th 
                      className="px-2 py-2 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider cursor-pointer hover:bg-neutral-100 transition-colors select-none"
                      onClick={() => handleSort('threes')}
                    >
                      <div className="flex items-center justify-end">
                        3PM
                        <SortIcon field="threes" />
                      </div>
                    </th>
                    <th 
                      className="px-2 py-2 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider cursor-pointer hover:bg-neutral-100 transition-colors select-none"
                      onClick={() => handleSort('points')}
                    >
                      <div className="flex items-center justify-end">
                        PTS
                        <SortIcon field="points" />
                      </div>
                    </th>
                    <th 
                      className="px-2 py-2 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider cursor-pointer hover:bg-neutral-100 transition-colors select-none"
                      onClick={() => handleSort('rebounds')}
                    >
                      <div className="flex items-center justify-end">
                        REB
                        <SortIcon field="rebounds" />
                      </div>
                    </th>
                    <th 
                      className="px-2 py-2 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider cursor-pointer hover:bg-neutral-100 transition-colors select-none"
                      onClick={() => handleSort('assists')}
                    >
                      <div className="flex items-center justify-end">
                        AST
                        <SortIcon field="assists" />
                      </div>
                    </th>
                    <th 
                      className="px-2 py-2 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider cursor-pointer hover:bg-neutral-100 transition-colors select-none"
                      onClick={() => handleSort('steals')}
                    >
                      <div className="flex items-center justify-end">
                        STL
                        <SortIcon field="steals" />
                      </div>
                    </th>
                    <th 
                      className="px-2 py-2 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider cursor-pointer hover:bg-neutral-100 transition-colors select-none"
                      onClick={() => handleSort('blocks')}
                    >
                      <div className="flex items-center justify-end">
                        BLK
                        <SortIcon field="blocks" />
                      </div>
                    </th>
                    <th 
                      className="px-2 py-2 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider cursor-pointer hover:bg-neutral-100 transition-colors select-none"
                      onClick={() => handleSort('turnovers')}
                    >
                      <div className="flex items-center justify-end">
                        TO
                        <SortIcon field="turnovers" />
                      </div>
                    </th>
                    <th 
                      className="px-2 py-2 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider cursor-pointer hover:bg-neutral-100 transition-colors select-none"
                      onClick={() => handleSort('usage_pct')}
                    >
                      <div className="flex items-center justify-end">
                        USG%
                        <SortIcon field="usage_pct" />
                      </div>
                    </th>
                    <th 
                      className="px-2 py-2 text-center text-xs font-semibold text-gray-600 uppercase tracking-wider cursor-pointer hover:bg-neutral-100 transition-colors select-none"
                      onClick={() => handleSort('status')}
                    >
                      <div className="flex items-center justify-center">
                        Status
                        <SortIcon field="status" />
                      </div>
                    </th>
                    <th 
                      className="px-2 py-2 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider cursor-pointer hover:bg-neutral-100 transition-colors select-none"
                      onClick={() => handleSort('injury')}
                    >
                      <div className="flex items-center">
                        Injury
                        <SortIcon field="injury" />
                      </div>
                    </th>
                    <th 
                      className="px-2 py-2 text-center text-xs font-semibold text-gray-600 uppercase tracking-wider cursor-pointer hover:bg-neutral-100 transition-colors select-none"
                      onClick={() => handleSort('lastGame')}
                    >
                      <div className="flex items-center justify-center">
                        Last Game
                        <SortIcon field="lastGame" />
                      </div>
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-100">
                  {filteredPlayers.map((player: WaiverPlayer, idx: number) => {
                    const trendColor = getTrendColor(player.trend);
                    const trendColorClass = getColorClass(trendColor);
                    const statusColor = player.status === 'W' ? 'text-yellow-600' : 'text-green-600';
                    
                    // Format injury status with color
                    let injuryColor = 'text-gray-400';
                    let injuryText = '-';
                    if (player.injury_status) {
                      const injuryUpper = player.injury_status.toUpperCase();
                      if (['INJ', 'O', 'OUT', 'IR', 'SUSP', 'PUP', 'NA'].includes(injuryUpper)) {
                        injuryColor = 'text-red-600';
                      } else if (['DTD', 'QUES', 'Q'].includes(injuryUpper)) {
                        injuryColor = 'text-yellow-600';
                      } else {
                        injuryColor = 'text-gray-600';
                      }
                      injuryText = injuryUpper;
                      if (player.injury_note) {
                        const truncated = player.injury_note.length > 10 
                          ? player.injury_note.substring(0, 10) + '...' 
                          : player.injury_note;
                        injuryText += ` ${truncated}`;
                      }
                    }

                    // Calculate days since last game and apply color
                    let lastGameColor = 'text-gray-600';
                    if (player.last_game_date) {
                      const lastGameDate = new Date(player.last_game_date);
                      const today = new Date();
                      const daysDiff = Math.floor((today.getTime() - lastGameDate.getTime()) / (1000 * 60 * 60 * 24));
                      
                      if (daysDiff > 7) {
                        lastGameColor = 'text-red-600';
                      } else if (daysDiff > 3) {
                        lastGameColor = 'text-orange-600';
                      }
                    }

                    // Check if player has injury (serious injury statuses)
                    const hasInjury = player.injury_status && 
                      ['INJ', 'O', 'OUT', 'IR', 'SUSP', 'PUP', 'NA'].includes(player.injury_status.toUpperCase());

                    return (
                      <tr key={idx} className={`group transition-colors ${
                        hasInjury ? 'bg-red-50 hover:bg-red-100' : 'hover:bg-neutral-50'
                      }`}>
                        <td className={`sticky left-0 z-10 w-12 min-w-[3rem] px-2 py-1.5 text-center text-xs text-gray-500 transition-colors ${
                          hasInjury ? 'bg-red-50 group-hover:bg-red-100' : 'bg-white group-hover:bg-neutral-50'
                        }`}>
                          {idx + 1}
                        </td>
                        <td className={`px-2 py-1.5 text-center text-xs font-medium ${
                          player.rank 
                            ? player.rank <= 25 
                              ? 'text-green-600' 
                              : player.rank <= 75 
                                ? 'text-blue-600' 
                                : player.rank <= 150 
                                  ? 'text-gray-600' 
                                  : 'text-gray-400'
                            : 'text-gray-400'
                        }`}>
                          {player.rank ?? '-'}
                        </td>
                        <td className={`sticky left-12 z-10 px-2 py-1.5 whitespace-nowrap text-xs font-medium shadow-[2px_0_4px_-2px_rgba(0,0,0,0.1)] transition-colors ${
                          hasInjury ? 'bg-red-50 group-hover:bg-red-100' : 'bg-white group-hover:bg-neutral-50'
                        }`}>
                          <div className="flex items-center gap-2">
                            <button
                              onClick={() => setSelectedPlayer({ id: player.player_id ?? null, name: player.name })}
                              className="text-cyan-600 hover:text-cyan-700 hover:underline transition-colors cursor-pointer"
                            >
                              {player.name}
                            </button>
                            {player.has_back_to_back && (
                              <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-semibold bg-green-100 text-green-800" title="Back-to-back games (today & tomorrow)">
                                B2B
                              </span>
                            )}
                          </div>
                        </td>
                        <td className={`px-2 py-1.5 text-center text-xs ${
                          player.remaining_games === 0 ? 'text-gray-400' :
                          player.remaining_games >= 4 ? 'text-green-600' :
                          player.remaining_games > 2 ? 'text-yellow-600' : 'text-red-600'
                        }`}>
                          ({player.remaining_games}/{player.total_games})
                        </td>
                        <td className={`px-2 py-1.5 text-center text-xs ${
                          player.next_week_games === 0 ? 'text-gray-400' :
                          player.next_week_games >= 4 ? 'text-green-600' :
                          player.next_week_games > 2 ? 'text-yellow-600' : 'text-red-600'
                        }`}>
                          {player.next_week_games}
                        </td>
                        <td className="px-2 py-1.5 text-center text-xs text-gray-600">
                          {player.stats?.games_count ?? '-'}
                        </td>
                        <td className={`px-2 py-1.5 text-right text-xs ${trendColorClass}`}>
                          {player.trend > 0 ? '+' : ''}{player.trend.toFixed(1)}
                        </td>
                        <td className="px-2 py-1.5 text-right text-xs text-gray-600">
                          {player.minutes.toFixed(1)}m
                        </td>
                        {player.stats ? (
                          <>
                            <StatCell 
                              statName="FGM" 
                              value={player.stats.fgm}
                              aggMode={lookback === 'last' ? 'last' : (aggMode as 'avg' | 'sum')}
                            />
                            <StatCell 
                              statName="FGA" 
                              value={player.stats.fga}
                              aggMode={lookback === 'last' ? 'last' : (aggMode as 'avg' | 'sum')}
                            />
                            <StatCell
                              statName="FG%"
                              value={player.stats.fg_pct}
                              aggMode={lookback === 'last' ? 'last' : (aggMode as 'avg' | 'sum')}
                            />
                            <StatCell 
                              statName="FTM" 
                              value={player.stats.ftm}
                              aggMode={lookback === 'last' ? 'last' : (aggMode as 'avg' | 'sum')}
                            />
                            <StatCell 
                              statName="FTA" 
                              value={player.stats.fta}
                              aggMode={lookback === 'last' ? 'last' : (aggMode as 'avg' | 'sum')}
                            />
                            <StatCell
                              statName="FT%"
                              value={player.stats.ft_pct}
                              aggMode={lookback === 'last' ? 'last' : (aggMode as 'avg' | 'sum')}
                            />
                            <StatCell 
                              statName="3PM" 
                              value={player.stats.threes}
                              aggMode={lookback === 'last' ? 'last' : (aggMode as 'avg' | 'sum')}
                            />
                            <StatCell 
                              statName="PTS" 
                              value={player.stats.points}
                              aggMode={lookback === 'last' ? 'last' : (aggMode as 'avg' | 'sum')}
                            />
                            <StatCell 
                              statName="REB" 
                              value={player.stats.rebounds}
                              aggMode={lookback === 'last' ? 'last' : (aggMode as 'avg' | 'sum')}
                            />
                            <StatCell 
                              statName="AST" 
                              value={player.stats.assists}
                              aggMode={lookback === 'last' ? 'last' : (aggMode as 'avg' | 'sum')}
                            />
                            <StatCell 
                              statName="STL" 
                              value={player.stats.steals}
                              aggMode={lookback === 'last' ? 'last' : (aggMode as 'avg' | 'sum')}
                            />
                            <StatCell 
                              statName="BLK" 
                              value={player.stats.blocks}
                              aggMode={lookback === 'last' ? 'last' : (aggMode as 'avg' | 'sum')}
                            />
                            <StatCell 
                              statName="TO" 
                              value={player.stats.turnovers}
                              aggMode={lookback === 'last' ? 'last' : (aggMode as 'avg' | 'sum')}
                            />
                            <StatCell 
                              statName="USG%" 
                              value={player.stats.usage_pct}
                              aggMode={lookback === 'last' ? 'last' : (aggMode as 'avg' | 'sum')}
                            />
                          </>
                        ) : (
                          <td colSpan={14} className="px-2 py-1.5 text-center text-xs text-gray-500">
                            N/A
                          </td>
                        )}
                        <td className={`px-2 py-1.5 text-center text-xs ${statusColor}`}>
                          {player.status}
                        </td>
                        <td className={`px-2 py-1.5 text-left text-xs ${injuryColor}`} title={player.injury_note}>
                          {injuryText}
                        </td>
                        <td className={`px-2 py-1.5 text-center text-xs ${lastGameColor}`}>
                          {player.last_game_date || '-'}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
              </div>
            )}
          </div>

          {/* Right column - Team Schedules (desktop only) */}
          {scheduleCollapsed ? (
            <div className="hidden lg:block fixed right-4 top-24 z-20">
              <button
                onClick={() => setScheduleCollapsed(false)}
                className="card p-3 hover:bg-neutral-50 transition-colors shadow-lg"
                title="Show team schedules"
              >
                <svg className="w-6 h-6 text-neutral-900" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                </svg>
              </button>
            </div>
          ) : (
            <div className="hidden lg:block lg:col-span-4 space-y-4">
              {scheduleLoading || !teamSchedule ? (
                <>
                  <TeamScheduleCard
                    teams={[]}
                    weekNumber={0}
                    weekType="current"
                    loading={true}
                    onCollapse={handleCollapseSchedule}
                  />
                  <TeamScheduleCard
                    teams={[]}
                    weekNumber={0}
                    weekType="next"
                    loading={true}
                    onCollapse={handleCollapseSchedule}
                  />
                </>
              ) : (
                <>
                  <TeamScheduleCard
                    teams={teamSchedule.teams}
                    weekNumber={teamSchedule.current_week}
                    weekType="current"
                    loading={false}
                    onCollapse={handleCollapseSchedule}
                  />
                  <TeamScheduleCard
                    teams={teamSchedule.teams}
                    weekNumber={teamSchedule.next_week}
                    weekType="next"
                    loading={false}
                    onCollapse={handleCollapseSchedule}
                  />
                </>
              )}
            </div>
          )}
        </div>
      </div>

      {selectedPlayer && (
        <PlayerStatsModal
          playerId={selectedPlayer.id}
          playerName={selectedPlayer.name}
          isOpen={!!selectedPlayer}
          onClose={() => setSelectedPlayer(null)}
        />
      )}
    </Layout>
  );
}

