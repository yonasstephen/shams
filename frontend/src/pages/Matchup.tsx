/**
 * Matchup projection page
 */

import { useState, useEffect } from 'react';
import { Layout } from '../components/Layout';
import { StatCell } from '../components/StatCell';
import { RemainingDaysProjection } from '../components/RemainingDaysProjection';
import { PlayerStatsModal } from '../components/PlayerStatsModal';
import { Dropdown } from '../components/Dropdown';
import { api } from '../services/api';
import { useLeague } from '../context/LeagueContext';
import { useMatchup } from '../context/MatchupContext';
import type { PlayerContribution, LeagueInfo, AllMatchupsResponse } from '../types/api';
import { getMarginColorClass } from '../utils/statColors';

type ContribSortField = 'name' | 'games' | string; // string for stat IDs
type SortDirection = 'asc' | 'desc';

export function Matchup() {
  const { leagues, defaultLeagueKey, currentWeek, totalWeeks } = useLeague();
  const { state, updateState } = useMatchup();
  const [leagueKey, setLeagueKey] = useState('');
  const [loading, setLoading] = useState(false);
  const [selectedPlayer, setSelectedPlayer] = useState<{ id: number; name: string } | null>(null);
  const [allMatchups, setAllMatchups] = useState<AllMatchupsResponse | null>(null);
  const [selectedTeamKey, setSelectedTeamKey] = useState<string>('');
  const [loadingMatchups, setLoadingMatchups] = useState(false);

  // Auto-collapse matchups list on mobile screens
  useEffect(() => {
    const handleResize = () => {
      if (window.innerWidth < 768 && !state.isMatchupListCollapsed) {
        // Auto-collapse on mobile if not already collapsed
        updateState({ isMatchupListCollapsed: true });
      }
    };
    
    // Check on initial load
    handleResize();
    
    // Add resize listener
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []); // Only run once on mount
  
  // Destructure state from context
  const { 
    week, 
    projectionMode,
    optimizeUserRoster,
    optimizeOpponentRoster,
    matchupData, 
    error,
    isMatchupListCollapsed,
    contribSortField, 
    contribSortDirection,
    opponentContribSortField,
    opponentContribSortDirection,
    projectionSortField,
    projectionSortDirection,
    opponentProjectionSortField,
    opponentProjectionSortDirection
  } = state;

  useEffect(() => {
    // Use default league key from context
    if (defaultLeagueKey) {
      setLeagueKey(defaultLeagueKey);
      // Clear matchup data and selected team when league changes
      updateState({ matchupData: null, error: null });
      setSelectedTeamKey('');
      setAllMatchups(null);
    } else if (leagues.length > 0) {
      setLeagueKey(leagues[0].league_key);
      // Clear matchup data and selected team when league changes
      updateState({ matchupData: null, error: null });
      setSelectedTeamKey('');
      setAllMatchups(null);
    }
  }, [defaultLeagueKey, leagues]);

  // Fetch all matchups when league/week/projection mode changes
  useEffect(() => {
    if (!leagueKey || !defaultLeagueKey) return;
    
    const fetchAllMatchups = async () => {
      setLoadingMatchups(true);
      // Clear selected team when starting to fetch new matchups
      setSelectedTeamKey('');
      try {
        const data = await api.getAllMatchups(leagueKey.trim(), week, projectionMode);
        setAllMatchups(data);
        
        // Always reset to user's team when league changes
        setSelectedTeamKey(data.user_team_key);
      } catch (err: any) {
        console.error('Failed to fetch all matchups:', err);
      } finally {
        setLoadingMatchups(false);
      }
    };
    
    fetchAllMatchups();
  }, [leagueKey, week, projectionMode]);

  // Auto-fetch detailed matchup when selected team changes
  useEffect(() => {
    if (!leagueKey || !defaultLeagueKey || !selectedTeamKey) return;
    
    // Don't fetch detailed matchup while all matchups are still loading
    if (loadingMatchups) return;
    
    // If we have matchup data in context, check if it's for the selected week and projection mode
    if (matchupData) {
      const selectedWeek = week !== undefined ? week : currentWeek;
      const dataWeek = matchupData.week;
      const dataProjectionMode = matchupData.projection_mode;
      
      // Only refetch if the week selection, projection mode, optimization flags, or team changed
      if ((selectedWeek !== undefined && dataWeek !== selectedWeek) || 
          dataProjectionMode !== projectionMode ||
          matchupData.optimize_user_roster !== optimizeUserRoster ||
          matchupData.optimize_opponent_roster !== optimizeOpponentRoster ||
          matchupData.user_team.team_key !== selectedTeamKey) {
        handleFetch();
      }
      // If weeks, projection mode, optimization flags, and team match, don't refetch - use cached data
    } else {
      // No data in context, fetch it
      handleFetch();
    }
  }, [leagueKey, week, projectionMode, optimizeUserRoster, optimizeOpponentRoster, selectedTeamKey, loadingMatchups]);

  const handleFetch = async () => {
    if (!leagueKey.trim()) {
      updateState({ error: 'Please enter a league key' });
      return;
    }

    if (!selectedTeamKey) {
      return;
    }

    setLoading(true);
    updateState({ error: null });
    // Don't clear matchupData here - let the overlay show over existing data

    try {
      const data = await api.getMatchupProjection(
        leagueKey.trim(),
        week,
        projectionMode,
        selectedTeamKey,
        optimizeUserRoster,
        optimizeOpponentRoster
      );
      updateState({ matchupData: data, error: null });
    } catch (err: any) {
      let errorMessage = 'Failed to fetch matchup projection. Please try again.';
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

  const handlePreviousWeek = () => {
    const currentWeek = week !== undefined ? week : matchupData?.week;
    if (currentWeek && currentWeek > 1) {
      updateState({ week: currentWeek - 1 });
    }
  };

  const handleNextWeek = () => {
    const currentWeek = week !== undefined ? week : matchupData?.week;
    if (currentWeek) {
      updateState({ week: currentWeek + 1 });
    }
  };

  const handleContribSort = (field: ContribSortField) => {
    if (contribSortField === field) {
      // Toggle direction if clicking the same field
      updateState({ contribSortDirection: contribSortDirection === 'asc' ? 'desc' : 'asc' });
    } else {
      // New field, default to descending for stats, ascending for name
      updateState({ 
        contribSortField: field,
        contribSortDirection: field === 'name' ? 'asc' : 'desc'
      });
    }
  };

  const handleOpponentContribSort = (field: ContribSortField) => {
    if (opponentContribSortField === field) {
      // Toggle direction if clicking the same field
      updateState({ opponentContribSortDirection: opponentContribSortDirection === 'asc' ? 'desc' : 'asc' });
    } else {
      // New field, default to descending for stats, ascending for name
      updateState({ 
        opponentContribSortField: field,
        opponentContribSortDirection: field === 'name' ? 'asc' : 'desc'
      });
    }
  };

  const handleProjectionSort = (field: ContribSortField) => {
    if (projectionSortField === field) {
      // Toggle direction if clicking the same field
      updateState({ projectionSortDirection: projectionSortDirection === 'asc' ? 'desc' : 'asc' });
    } else {
      // New field, default to descending for stats, ascending for name
      updateState({ 
        projectionSortField: field,
        projectionSortDirection: field === 'name' ? 'asc' : 'desc'
      });
    }
  };

  const handleOpponentProjectionSort = (field: ContribSortField) => {
    if (opponentProjectionSortField === field) {
      // Toggle direction if clicking the same field
      updateState({ opponentProjectionSortDirection: opponentProjectionSortDirection === 'asc' ? 'desc' : 'asc' });
    } else {
      // New field, default to descending for stats, ascending for name
      updateState({ 
        opponentProjectionSortField: field,
        opponentProjectionSortDirection: field === 'name' ? 'asc' : 'desc'
      });
    }
  };

  const getSortedContributions = (
    contributions: PlayerContribution[], 
    sortField: ContribSortField,
    sortDirection: SortDirection
  ): PlayerContribution[] => {
    const sorted = [...contributions];
    
    sorted.sort((a, b) => {
      // First priority: players on roster come before those not on roster
      if (a.is_on_roster_today !== b.is_on_roster_today) {
        return a.is_on_roster_today ? -1 : 1;
      }

      // Second priority: sort by selected field
      let aValue: any;
      let bValue: any;

      if (sortField === 'name') {
        aValue = a.player_name.toLowerCase();
        bValue = b.player_name.toLowerCase();
      } else if (sortField === 'games') {
        aValue = a.remaining_games;
        bValue = b.remaining_games;
      } else {
        // Sorting by stat ID
        aValue = a.stats?.[sortField] ?? -1;
        bValue = b.stats?.[sortField] ?? -1;
      }

      // Handle string comparison
      if (typeof aValue === 'string') {
        const cmp = aValue.localeCompare(bValue);
        return sortDirection === 'asc' ? cmp : -cmp;
      }

      // Handle number comparison
      const cmp = aValue - bValue;
      return sortDirection === 'asc' ? cmp : -cmp;
    });

    return sorted;
  };

  const ContribSortIcon = ({ 
    field, 
    currentSortField, 
    currentSortDirection 
  }: { 
    field: ContribSortField;
    currentSortField: ContribSortField;
    currentSortDirection: SortDirection;
  }) => {
    if (currentSortField !== field) {
      return <span className="text-gray-400 ml-1">↕</span>;
    }
    return <span className="text-gray-900 ml-1">{currentSortDirection === 'asc' ? '↑' : '↓'}</span>;
  };

  return (
    <Layout>
      <div className="px-4 py-4 md:py-6">
        <h1 className="text-2xl md:text-3xl font-bold text-gray-900 mb-4 md:mb-6">Matchup Projection</h1>

        {/* League requirement warning */}
        {!defaultLeagueKey && (
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
            <p className="text-blue-800 font-semibold">No league selected</p>
            <p className="text-blue-700 text-sm mt-1">
              Please <a href="/" className="underline font-medium">select a league</a> from the home page first, or enter a league key below.
            </p>
          </div>
        )}

        {/* GLOBAL CONTROLS BAR */}
        <div className="bg-gray-50 rounded-lg shadow-md p-4 md:p-6 mb-4 md:mb-6 border border-gray-200">
          {defaultLeagueKey && (
            <div className="mb-3 md:mb-4 text-xs md:text-sm text-gray-600">
              Using league: <span className="font-semibold">{leagues.find((l: LeagueInfo) => l.league_key === defaultLeagueKey)?.name || defaultLeagueKey}</span>
            </div>
          )}
          {!defaultLeagueKey && (
            <div className="mb-3 md:mb-4">
              <label className="block text-sm font-medium text-gray-700 mb-2">
                League Key
              </label>
              <input
                type="text"
                value={leagueKey}
                onChange={(e) => setLeagueKey(e.target.value)}
                placeholder="Enter league key..."
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          )}

          <div className="space-y-3">
            {/* Dropdowns row */}
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="block text-xs md:text-sm font-medium text-gray-700 mb-2">
                  Week
                </label>
                {totalWeeks ? (
                  <Dropdown
                    value={week || currentWeek || ''}
                    onChange={(value) => updateState({ week: value ? parseInt(String(value)) : undefined })}
                    disabled={loading}
                    options={Array.from({ length: totalWeeks }, (_, i) => i + 1).map((weekNum) => ({
                      value: weekNum,
                      label: `Week ${weekNum}${weekNum === currentWeek ? ' (current)' : ''}`,
                    }))}
                    className="w-full"
                  />
                ) : (
                  <input
                    type="number"
                    value={week || ''}
                    onChange={(e) => updateState({ week: e.target.value ? parseInt(e.target.value) : undefined })}
                    placeholder="Current week"
                    min="1"
                    disabled={loading}
                    className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
                  />
                )}
              </div>
              <div>
                <label className="block text-xs md:text-sm font-medium text-gray-700 mb-2">
                  Projection Mode
                </label>
                <Dropdown
                  value={projectionMode}
                  onChange={(value) => updateState({ projectionMode: String(value) })}
                  disabled={loading}
                  options={[
                    { value: 'season', label: 'Season Avg' },
                    { value: 'last3', label: 'Last 3 Games' },
                    { value: 'last7', label: 'Last 7 Games' },
                    { value: 'last7d', label: 'Last 7 Days' },
                    { value: 'last30d', label: 'Last 30 Days' },
                  ]}
                  className="w-full"
                />
              </div>
            </div>

            {/* Roster Optimization Checkboxes */}
            <div className="flex flex-col gap-2 mt-2">
              <label className="flex items-center space-x-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={optimizeUserRoster}
                  onChange={(e) => updateState({ optimizeUserRoster: e.target.checked })}
                  disabled={loading}
                  className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
                />
                <span className="text-xs md:text-sm text-gray-700">
                  Optimize My Roster <span className="text-gray-500">(maximize active players)</span>
                </span>
              </label>
              <label className="flex items-center space-x-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={optimizeOpponentRoster}
                  onChange={(e) => updateState({ optimizeOpponentRoster: e.target.checked })}
                  disabled={loading}
                  className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
                />
                <span className="text-xs md:text-sm text-gray-700">
                  Optimize Opponent Roster <span className="text-gray-500">(counter sandbagging)</span>
                </span>
              </label>
            </div>

            {/* Buttons row */}
            <div className="grid grid-cols-2 md:flex md:items-center gap-2">
              <button
                onClick={handlePreviousWeek}
                disabled={loading || !matchupData}
                className="px-3 md:px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed text-xs md:text-sm font-medium"
              >
                <span className="md:hidden">← Prev</span>
                <span className="hidden md:inline">← Previous Week</span>
              </button>
              <button
                onClick={handleNextWeek}
                disabled={loading || !matchupData}
                className="px-3 md:px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed text-xs md:text-sm font-medium"
              >
                <span className="md:hidden">Next →</span>
                <span className="hidden md:inline">Next Week →</span>
              </button>
              <button
                onClick={handleFetch}
                disabled={loading}
                className="col-span-2 md:col-span-1 px-3 md:px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-xs md:text-sm font-medium flex items-center justify-center gap-2"
                title="Refresh matchup data"
              >
                <svg 
                  className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`}
                  fill="none" 
                  stroke="currentColor" 
                  viewBox="0 0 24 24"
                >
                  <path 
                    strokeLinecap="round" 
                    strokeLinejoin="round" 
                    strokeWidth={2} 
                    d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" 
                  />
                </svg>
                Refresh
              </button>
            </div>
          </div>
        </div>

        {/* ALL MATCHUPS SECTION (COLLAPSIBLE) */}
        {loadingMatchups && (
          <div className="bg-white rounded-lg shadow-md overflow-hidden mb-6 border border-gray-200">
            <div className="p-6 text-center">
              <div className="inline-block animate-spin rounded-full h-10 w-10 border-b-2 border-blue-600 mb-3"></div>
              <p className="text-gray-700 font-medium">Loading all matchups...</p>
              <p className="text-gray-500 text-sm mt-1">Please wait while we fetch all league matchups</p>
            </div>
          </div>
        )}
        
        {!loadingMatchups && allMatchups && allMatchups.matchups.length > 0 && (
          <div className="bg-white rounded-lg shadow-md overflow-hidden mb-4 md:mb-6 border border-gray-200">
            {/* Section Header with Collapse Toggle */}
            <div className="p-3 md:p-4 border-b border-gray-200 flex items-center justify-between bg-white">
              <h2 className="text-lg md:text-xl font-semibold text-gray-900">
                All Matchups
              </h2>
              <button
                onClick={() => updateState({ isMatchupListCollapsed: !isMatchupListCollapsed })}
                className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
                aria-label={isMatchupListCollapsed ? "Expand matchups" : "Collapse matchups"}
              >
                <svg 
                  className={`w-5 h-5 text-gray-600 transition-transform duration-200 ${isMatchupListCollapsed ? 'rotate-0' : 'rotate-180'}`}
                  fill="none" 
                  stroke="currentColor" 
                  viewBox="0 0 24 24"
                >
                  <path 
                    strokeLinecap="round" 
                    strokeLinejoin="round" 
                    strokeWidth={2} 
                    d="M19 9l-7 7-7-7" 
                  />
                </svg>
              </button>
            </div>

            {/* Collapsible Content */}
            <div 
              className={`transition-all duration-300 ease-in-out overflow-hidden ${
                isMatchupListCollapsed ? 'max-h-0' : 'max-h-[2000px]'
              }`}
            >
              <div className="overflow-x-auto touch-scroll">
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-2 md:px-3 py-1.5 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Team
                      </th>
                      <th className="px-2 md:px-3 py-1.5 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Score
                      </th>
                      <th className="px-2 md:px-3 py-1.5 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">
                        
                      </th>
                      <th className="px-2 md:px-3 py-1.5 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Score
                      </th>
                      <th className="px-2 md:px-3 py-1.5 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Team
                      </th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-gray-200">
                    {allMatchups.matchups.map((matchup) => {
                      const teamA = matchup.teams[0];
                      const teamB = matchup.teams[1];
                      const isUserTeamA = teamA.team_key === allMatchups.user_team_key;
                      const isUserTeamB = teamB.team_key === allMatchups.user_team_key;
                      const isSelected = selectedTeamKey === teamA.team_key || selectedTeamKey === teamB.team_key;
                      
                      return (
                        <tr
                          key={`${teamA.team_key}-${teamB.team_key}`}
                          onClick={() => setSelectedTeamKey(teamA.team_key)}
                          className={`cursor-pointer transition-colors ${
                            isSelected 
                              ? 'bg-blue-100 border-l-4 border-blue-500 hover:bg-blue-200' 
                              : 'hover:bg-gray-50'
                          }`}
                        >
                          <td className="px-2 md:px-3 py-1.5 whitespace-nowrap">
                            <div className="flex items-center gap-1.5">
                              <div className="text-xs font-medium text-gray-900">
                                {teamA.team_name}
                              </div>
                              {isUserTeamA && (
                                <span className="px-1.5 py-0.5 text-[10px] font-semibold rounded bg-blue-600 text-white">
                                  YOU
                                </span>
                              )}
                            </div>
                          </td>
                          <td className={`px-2 md:px-3 py-1.5 text-center text-xs font-semibold ${
                            teamA.team_points > teamB.team_points ? 'text-green-600' :
                            teamA.team_points < teamB.team_points ? 'text-red-600' :
                            'text-gray-900'
                          }`}>
                            {teamA.team_points.toFixed(0)}
                          </td>
                          <td className="px-2 md:px-3 py-1.5 text-center text-xs text-gray-400 font-medium">
                            vs
                          </td>
                          <td className={`px-2 md:px-3 py-1.5 text-center text-xs font-semibold ${
                            teamB.team_points > teamA.team_points ? 'text-green-600' :
                            teamB.team_points < teamA.team_points ? 'text-red-600' :
                            'text-gray-900'
                          }`}>
                            {teamB.team_points.toFixed(0)}
                          </td>
                          <td className="px-2 md:px-3 py-1.5 whitespace-nowrap">
                            <div className="flex items-center justify-end gap-1.5">
                              <div className="text-xs font-medium text-gray-900">
                                {teamB.team_name}
                              </div>
                              {isUserTeamB && (
                                <span className="px-1.5 py-0.5 text-[10px] font-semibold rounded bg-blue-600 text-white">
                                  YOU
                                </span>
                              )}
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {loading && !matchupData && (
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-8 mb-6">
            <div className="text-center">
              <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mb-4"></div>
              <p className="text-lg font-semibold text-blue-700">Loading matchup data...</p>
            </div>
          </div>
        )}

        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
            <p className="text-red-600">{error}</p>
          </div>
        )}

        {/* SELECTED MATCHUP DETAILS SECTION */}
        {matchupData && (
          <div className="relative">
            {/* Loading overlay when changing weeks */}
            {loading && (
              <div className="absolute inset-0 bg-white bg-opacity-75 flex items-center justify-center z-10 rounded-lg">
                <div className="text-center">
                  <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mb-4"></div>
                  <p className="text-lg font-semibold text-gray-700">Loading Week {week || '...'}</p>
                </div>
              </div>
            )}
            
            <div className="space-y-4 md:space-y-6">
            {/* Section Header */}
            <div className="bg-white rounded-lg shadow-md p-4 md:p-6 border border-gray-200">
              <div className="mb-3 md:mb-4">
                <h2 className="text-xl md:text-2xl font-bold text-gray-900 mb-1">
                  Selected Matchup Details
                </h2>
                <p className="text-xs md:text-sm text-gray-500">
                  Week {matchupData.week} • {matchupData.week_start} to {matchupData.week_end}
                </p>
              </div>
              <div className="border-t border-gray-200 pt-3 md:pt-4">
                <div className="flex items-center justify-center gap-4 md:gap-8 text-sm md:text-lg">
                  <div className="text-center">
                    <div className="font-semibold text-gray-700 mb-1 text-xs md:text-base truncate max-w-[120px] md:max-w-none">{matchupData.user_team.team_name}</div>
                    <div className="flex items-center gap-1 md:gap-2">
                      <span className={`text-xl md:text-2xl font-bold ${
                        matchupData.user_team.team_points > matchupData.opponent_team.team_points ? 'text-green-600' :
                        matchupData.user_team.team_points < matchupData.opponent_team.team_points ? 'text-red-600' :
                        'text-gray-900'
                      }`}>
                        {matchupData.user_team.team_points.toFixed(0)}
                      </span>
                      <span className={`text-sm md:text-lg ${
                        matchupData.user_team.projected_team_points > matchupData.opponent_team.projected_team_points ? 'text-green-600' :
                        matchupData.user_team.projected_team_points < matchupData.opponent_team.projected_team_points ? 'text-red-600' :
                        'text-gray-900'
                      }`}>
                        ({matchupData.user_team.projected_team_points.toFixed(0)}-{matchupData.opponent_team.projected_team_points.toFixed(0)}{(matchupData.user_team.projected_team_ties ?? 0) > 0 ? `-${matchupData.user_team.projected_team_ties.toFixed(0)}` : ''})
                      </span>
                    </div>
                  </div>
                  <span className="text-2xl md:text-3xl text-gray-400 font-light">vs</span>
                  <div className="text-center">
                    <div className="font-semibold text-gray-700 mb-1 text-xs md:text-base truncate max-w-[120px] md:max-w-none">{matchupData.opponent_team.team_name}</div>
                    <div className="flex items-center gap-1 md:gap-2">
                      <span className={`text-xl md:text-2xl font-bold ${
                        matchupData.opponent_team.team_points > matchupData.user_team.team_points ? 'text-green-600' :
                        matchupData.opponent_team.team_points < matchupData.user_team.team_points ? 'text-red-600' :
                        'text-gray-900'
                      }`}>
                        {matchupData.opponent_team.team_points.toFixed(0)}
                      </span>
                      <span className={`text-sm md:text-lg ${
                        matchupData.opponent_team.projected_team_points > matchupData.user_team.projected_team_points ? 'text-green-600' :
                        matchupData.opponent_team.projected_team_points < matchupData.user_team.projected_team_points ? 'text-red-600' :
                        'text-gray-900'
                      }`}>
                        ({matchupData.opponent_team.projected_team_points.toFixed(0)}-{matchupData.user_team.projected_team_points.toFixed(0)}{(matchupData.opponent_team.projected_team_ties ?? 0) > 0 ? `-${matchupData.opponent_team.projected_team_ties.toFixed(0)}` : ''})
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Category Comparison */}
            <div className="bg-white rounded-lg shadow-md overflow-hidden border border-gray-200">
              <h3 className="text-lg md:text-xl font-semibold text-gray-900 p-4 md:p-6 pb-3 md:pb-4">
                Projected Category Totals
              </h3>
              <div className="overflow-x-auto touch-scroll">
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Category
                      </th>
                      <th className="px-3 py-3 text-right text-xs font-medium text-cyan-600 uppercase tracking-wider" colSpan={3}>
                        Current
                      </th>
                      <th className="px-3 py-3 text-right text-xs font-medium text-magenta-600 uppercase tracking-wider" colSpan={3}>
                        Projection
                      </th>
                    </tr>
                    <tr>
                      <th></th>
                      <th className="px-3 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                        {matchupData.user_team.team_name}
                      </th>
                      <th className="px-3 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                        {matchupData.opponent_team.team_name}
                      </th>
                      <th className="px-3 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                        Margin
                      </th>
                      <th className="px-3 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                        {matchupData.user_team.team_name}
                      </th>
                      <th className="px-3 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                        {matchupData.opponent_team.team_name}
                      </th>
                      <th className="px-3 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                        Margin
                      </th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-gray-200">
                    {matchupData.stat_categories.map((stat: any) => {
                      const statId = String(stat.stat_id);
                      if (stat.is_only_display_stat === 1) return null;

                      const statName = stat.display_name || stat.name || statId;
                      const isPercentage = statName.includes('%');
                      const isAscending = stat.sort_order === '0' || stat.sort_order === 0;

                      const userCurr = matchupData.user_current[statId] || 0;
                      const oppCurr = matchupData.opponent_current[statId] || 0;
                      const userProj = matchupData.user_projection[statId] || 0;
                      const oppProj = matchupData.opponent_projection[statId] || 0;

                      // Calculate margins
                      const currMargin = isAscending ? oppCurr - userCurr : userCurr - oppCurr;
                      const projMargin = isAscending ? oppProj - userProj : userProj - oppProj;

                      // Calculate individual stat margins (difference from opponent)
                      const userCurrMargin = isAscending ? oppCurr - userCurr : userCurr - oppCurr;
                      const oppCurrMargin = isAscending ? userCurr - oppCurr : oppCurr - userCurr;
                      const userProjMargin = isAscending ? oppProj - userProj : userProj - oppProj;
                      const oppProjMargin = isAscending ? userProj - oppProj : oppProj - userProj;

                      // Get gradated color classes based on margins
                      const userCurrColorClass = getMarginColorClass(statName, userCurrMargin);
                      const oppCurrColorClass = getMarginColorClass(statName, oppCurrMargin);
                      const currMarginColorClass = getMarginColorClass(statName, currMargin);
                      const userProjColorClass = getMarginColorClass(statName, userProjMargin);
                      const oppProjColorClass = getMarginColorClass(statName, oppProjMargin);
                      const projMarginColorClass = getMarginColorClass(statName, projMargin);

                      const formatValue = (val: number) => {
                        if (isPercentage) return `${(val * 100).toFixed(1)}%`;
                        return val.toFixed(2);
                      };

                      const formatMargin = (val: number) => {
                        if (isPercentage) return `${val > 0 ? '+' : ''}${(val * 100).toFixed(1)}%`;
                        return `${val > 0 ? '+' : ''}${val.toFixed(2)}`;
                      };

                      // Format percentage with attempts for FG% and FT%
                      const formatPercentageWithAttempts = (pct: number, made: number, attempts: number) => {
                        const pctFormatted = `${(pct * 100).toFixed(1)}%`;
                        const madeRounded = made.toFixed(0);
                        const attemptsRounded = attempts.toFixed(0);
                        return `${pctFormatted} (${madeRounded}/${attemptsRounded})`;
                      };

                      // Check if this is FG% or FT% for projected columns
                      const isFGPct = statName.includes('FG%') || statId === '5';
                      const isFTPct = statName.includes('FT%') || statId === '8';
                      
                      let userProjFormatted = formatValue(userProj);
                      let oppProjFormatted = formatValue(oppProj);
                      
                      if (isFGPct) {
                        const userFGM = matchupData.user_projection['_FGM'] || 0;
                        const userFGA = matchupData.user_projection['_FGA'] || 0;
                        const oppFGM = matchupData.opponent_projection['_FGM'] || 0;
                        const oppFGA = matchupData.opponent_projection['_FGA'] || 0;
                        userProjFormatted = formatPercentageWithAttempts(userProj, userFGM, userFGA);
                        oppProjFormatted = formatPercentageWithAttempts(oppProj, oppFGM, oppFGA);
                      } else if (isFTPct) {
                        const userFTM = matchupData.user_projection['_FTM'] || 0;
                        const userFTA = matchupData.user_projection['_FTA'] || 0;
                        const oppFTM = matchupData.opponent_projection['_FTM'] || 0;
                        const oppFTA = matchupData.opponent_projection['_FTA'] || 0;
                        userProjFormatted = formatPercentageWithAttempts(userProj, userFTM, userFTA);
                        oppProjFormatted = formatPercentageWithAttempts(oppProj, oppFTM, oppFTA);
                      }

                      return (
                        <tr key={statId} className="hover:bg-gray-50">
                          <td className="px-3 py-2 whitespace-nowrap text-sm font-medium text-gray-900">
                            {statName}
                          </td>
                          <td className={`px-3 py-2 text-right text-sm ${userCurrColorClass}`}>
                            {formatValue(userCurr)}
                          </td>
                          <td className={`px-3 py-2 text-right text-sm ${oppCurrColorClass}`}>
                            {formatValue(oppCurr)}
                          </td>
                          <td className={`px-3 py-2 text-right text-sm ${currMarginColorClass}`}>
                            {formatMargin(currMargin)}
                          </td>
                          <td className={`px-3 py-2 text-right text-sm ${userProjColorClass}`}>
                            {userProjFormatted}
                          </td>
                          <td className={`px-3 py-2 text-right text-sm ${oppProjColorClass}`}>
                            {oppProjFormatted}
                          </td>
                          <td className={`px-3 py-2 text-right text-sm ${projMarginColorClass}`}>
                            {formatMargin(projMargin)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Player Contributions - Side by Side */}
            {(matchupData.current_player_contributions.length > 0 || matchupData.opponent_current_player_contributions?.length > 0) && (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {/* User Roster Contributions */}
                {matchupData.current_player_contributions.length > 0 && (
                  <div className="bg-white rounded-lg shadow-md overflow-hidden border border-gray-200">
                    <h3 className="text-xl font-semibold text-gray-900 p-6 pb-4">
                      {matchupData.user_team.team_name} Roster Contributions
                    </h3>
                    <div className="overflow-x-auto">
                      <table className="min-w-full divide-y divide-gray-200">
                        <thead className="bg-gray-50">
                          <tr>
                            <th 
                              className="px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100 transition-colors select-none"
                              onClick={() => handleContribSort('name')}
                            >
                              <div className="flex items-center">
                                Player
                                <ContribSortIcon 
                                  field="name" 
                                  currentSortField={contribSortField}
                                  currentSortDirection={contribSortDirection}
                                />
                              </div>
                            </th>
                            <th 
                              className="px-3 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100 transition-colors select-none"
                              onClick={() => handleContribSort('games')}
                            >
                              <div className="flex items-center justify-center">
                                Games
                                <ContribSortIcon 
                                  field="games"
                                  currentSortField={contribSortField}
                                  currentSortDirection={contribSortDirection}
                                />
                              </div>
                            </th>
                            {matchupData.stat_categories
                              .filter((stat: any) => {
                                const statId = String(stat.stat_id);
                                const statName = stat.display_name || stat.name || '';
                                // Filter out FGM/A and FTM/A columns (redundant with FG% and FT%)
                                return statId !== '9004003' && statId !== '9007006' && !statName.includes('M/A');
                              })
                              .slice(0, 9)
                              .map((stat: any) => {
                                const statId = String(stat.stat_id);
                                return (
                                  <th 
                                    key={statId}
                                    className="px-3 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100 transition-colors select-none"
                                    onClick={() => handleContribSort(statId)}
                                  >
                                    <div className="flex items-center justify-end">
                                      {stat.abbr || stat.display_name}
                                      <ContribSortIcon 
                                        field={statId}
                                        currentSortField={contribSortField}
                                        currentSortDirection={contribSortDirection}
                                      />
                                    </div>
                                  </th>
                                );
                              })}
                          </tr>
                        </thead>
                        <tbody className="bg-white divide-y divide-gray-200">
                          {getSortedContributions(matchupData.current_player_contributions, contribSortField, contribSortDirection).map((contrib) => {
                        const gamesColor = contrib.remaining_games === 0 ? 'text-gray-400' :
                                          contrib.remaining_games >= 4 ? 'text-green-600' :
                                          contrib.remaining_games > 2 ? 'text-yellow-600' : 'text-red-600';

                        // Ensure stats and shooting are defined
                        const playerStats = contrib.stats || {};
                        const playerShooting = contrib.shooting || {};
                        
                        // Apply gray color to players no longer on roster
                        const playerNameColor = contrib.is_on_roster_today ? 'text-gray-900' : 'text-gray-400';

                        return (
                          <tr key={contrib.player_key} className="hover:bg-gray-50">
                            <td className="px-3 py-2 whitespace-nowrap text-sm font-medium">
                              {contrib.player_id ? (
                                <button
                                  onClick={() => setSelectedPlayer({ id: contrib.player_id!, name: contrib.player_name })}
                                  className="text-cyan-600 hover:text-cyan-700 hover:underline transition-colors cursor-pointer text-left"
                                >
                                  {contrib.player_name}
                                </button>
                              ) : (
                                <span className={playerNameColor}>{contrib.player_name}</span>
                              )}
                            </td>
                            <td className={`px-3 py-2 text-center text-sm ${gamesColor}`}>
                              ({contrib.remaining_games}/{contrib.total_games})
                            </td>
                            {matchupData.stat_categories
                              .filter((stat: any) => {
                                const statId = String(stat.stat_id);
                                const statName = stat.display_name || stat.name || '';
                                // Filter out FGM/A and FTM/A columns (redundant with FG% and FT%)
                                return statId !== '9004003' && statId !== '9007006' && !statName.includes('M/A');
                              })
                              .slice(0, 9)
                              .map((stat: any) => {
                                const statId = String(stat.stat_id);
                                const value = playerStats[statId] ?? 0;
                                const statName = stat.display_name || stat.name || '';

                                if (statName.includes('%')) {
                                  // For percentages, show with shooting attempts using StatCell
                                  const fgm = playerShooting?.fgm ?? 0;
                                  const fga = playerShooting?.fga ?? 0;
                                  const ftm = playerShooting?.ftm ?? 0;
                                  const fta = playerShooting?.fta ?? 0;

                                  if (statId === '5' && (fgm > 0 || fga > 0)) {
                                    return (
                                      <StatCell
                                        key={statId}
                                        statName="FG%"
                                        value={value}
                                        attempts={{ made: fgm, attempts: fga }}
                                        aggMode="sum"
                                      />
                                    );
                                  } else if (statId === '8' && (ftm > 0 || fta > 0)) {
                                    return (
                                      <StatCell
                                        key={statId}
                                        statName="FT%"
                                        value={value}
                                        attempts={{ made: ftm, attempts: fta }}
                                        aggMode="sum"
                                      />
                                    );
                                  } else {
                                    return (
                                      <StatCell
                                        key={statId}
                                        statName={statName}
                                        value={value}
                                        aggMode="sum"
                                      />
                                    );
                                  }
                                }

                                // Map stat IDs to stat names for color coding
                                let statNameForColor = statName;
                                if (statId === '10') statNameForColor = '3PM';
                                else if (statId === '12') statNameForColor = 'PTS';
                                else if (statId === '15') statNameForColor = 'REB';
                                else if (statId === '16') statNameForColor = 'AST';
                                else if (statId === '17') statNameForColor = 'STL';
                                else if (statId === '18') statNameForColor = 'BLK';
                                else if (statId === '19') statNameForColor = 'TO';

                                return (
                                  <StatCell
                                    key={statId}
                                    statName={statNameForColor}
                                    value={value}
                                    aggMode="sum"
                                  />
                                );
                              })}
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Opponent Roster Contributions */}
            {matchupData.opponent_current_player_contributions && matchupData.opponent_current_player_contributions.length > 0 && (
              <div className="bg-white rounded-lg shadow-md overflow-hidden border border-gray-200">
                <h3 className="text-xl font-semibold text-gray-900 p-6 pb-4">
                  {matchupData.opponent_team.team_name} Roster Contributions
                </h3>
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-gray-50">
                      <tr>
                        <th 
                          className="px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100 transition-colors select-none"
                          onClick={() => handleOpponentContribSort('name')}
                        >
                          <div className="flex items-center">
                            Player
                            <ContribSortIcon 
                              field="name" 
                              currentSortField={opponentContribSortField}
                              currentSortDirection={opponentContribSortDirection}
                            />
                          </div>
                        </th>
                        <th 
                          className="px-3 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100 transition-colors select-none"
                          onClick={() => handleOpponentContribSort('games')}
                        >
                          <div className="flex items-center justify-center">
                            Games
                            <ContribSortIcon 
                              field="games"
                              currentSortField={opponentContribSortField}
                              currentSortDirection={opponentContribSortDirection}
                            />
                          </div>
                        </th>
                        {matchupData.stat_categories
                          .filter((stat: any) => {
                            const statId = String(stat.stat_id);
                            const statName = stat.display_name || stat.name || '';
                            // Filter out FGM/A and FTM/A columns (redundant with FG% and FT%)
                            return statId !== '9004003' && statId !== '9007006' && !statName.includes('M/A');
                          })
                          .slice(0, 9)
                          .map((stat: any) => {
                            const statId = String(stat.stat_id);
                            return (
                              <th 
                                key={statId}
                                className="px-3 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100 transition-colors select-none"
                                onClick={() => handleOpponentContribSort(statId)}
                              >
                                <div className="flex items-center justify-end">
                                  {stat.abbr || stat.display_name}
                                  <ContribSortIcon 
                                    field={statId}
                                    currentSortField={opponentContribSortField}
                                    currentSortDirection={opponentContribSortDirection}
                                  />
                                </div>
                              </th>
                            );
                          })}
                      </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-200">
                      {getSortedContributions(matchupData.opponent_current_player_contributions, opponentContribSortField, opponentContribSortDirection).map((contrib) => {
                        const gamesColor = contrib.remaining_games === 0 ? 'text-gray-400' :
                                          contrib.remaining_games >= 4 ? 'text-green-600' :
                                          contrib.remaining_games > 2 ? 'text-yellow-600' : 'text-red-600';

                        // Ensure stats and shooting are defined
                        const playerStats = contrib.stats || {};
                        const playerShooting = contrib.shooting || {};
                        
                        // Apply gray color to players no longer on roster
                        const playerNameColor = contrib.is_on_roster_today ? 'text-gray-900' : 'text-gray-400';

                        return (
                          <tr key={contrib.player_key} className="hover:bg-gray-50">
                            <td className="px-3 py-2 whitespace-nowrap text-sm font-medium">
                              {contrib.player_id ? (
                                <button
                                  onClick={() => setSelectedPlayer({ id: contrib.player_id!, name: contrib.player_name })}
                                  className="text-cyan-600 hover:text-cyan-700 hover:underline transition-colors cursor-pointer text-left"
                                >
                                  {contrib.player_name}
                                </button>
                              ) : (
                                <span className={playerNameColor}>{contrib.player_name}</span>
                              )}
                            </td>
                            <td className={`px-3 py-2 text-center text-sm ${gamesColor}`}>
                              ({contrib.remaining_games}/{contrib.total_games})
                            </td>
                            {matchupData.stat_categories
                              .filter((stat: any) => {
                                const statId = String(stat.stat_id);
                                const statName = stat.display_name || stat.name || '';
                                // Filter out FGM/A and FTM/A columns (redundant with FG% and FT%)
                                return statId !== '9004003' && statId !== '9007006' && !statName.includes('M/A');
                              })
                              .slice(0, 9)
                              .map((stat: any) => {
                                const statId = String(stat.stat_id);
                                const value = playerStats[statId] ?? 0;
                                const statName = stat.display_name || stat.name || '';

                                if (statName.includes('%')) {
                                  // For percentages, show with shooting attempts using StatCell
                                  const fgm = playerShooting?.fgm ?? 0;
                                  const fga = playerShooting?.fga ?? 0;
                                  const ftm = playerShooting?.ftm ?? 0;
                                  const fta = playerShooting?.fta ?? 0;

                                  if (statId === '5' && (fgm > 0 || fga > 0)) {
                                    return (
                                      <StatCell
                                        key={statId}
                                        statName="FG%"
                                        value={value}
                                        attempts={{ made: fgm, attempts: fga }}
                                        aggMode="sum"
                                      />
                                    );
                                  } else if (statId === '8' && (ftm > 0 || fta > 0)) {
                                    return (
                                      <StatCell
                                        key={statId}
                                        statName="FT%"
                                        value={value}
                                        attempts={{ made: ftm, attempts: fta }}
                                        aggMode="sum"
                                      />
                                    );
                                  } else {
                                    return (
                                      <StatCell
                                        key={statId}
                                        statName={statName}
                                        value={value}
                                        aggMode="sum"
                                      />
                                    );
                                  }
                                }

                                // Map stat IDs to stat names for color coding
                                let statNameForColor = statName;
                                if (statId === '10') statNameForColor = '3PM';
                                else if (statId === '12') statNameForColor = 'PTS';
                                else if (statId === '15') statNameForColor = 'REB';
                                else if (statId === '16') statNameForColor = 'AST';
                                else if (statId === '17') statNameForColor = 'STL';
                                else if (statId === '18') statNameForColor = 'BLK';
                                else if (statId === '19') statNameForColor = 'TO';

                                return (
                                  <StatCell
                                    key={statId}
                                    statName={statNameForColor}
                                    value={value}
                                    aggMode="sum"
                                  />
                                );
                              })}
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}

            {/* User Remaining Days Projection */}
            {matchupData.remaining_days_projection && Object.keys(matchupData.remaining_days_projection).length > 0 && (
              <div>
                <div className="text-sm text-gray-600 mb-2 px-6 flex items-center gap-2 flex-wrap">
                  <span>
                    <span className="font-medium">Projections based on: </span>
                    {projectionMode === 'season' && 'Season Average'}
                    {projectionMode === 'last3' && 'Last 3 Games Average'}
                    {projectionMode === 'last7' && 'Last 7 Games Average'}
                    {projectionMode === 'last7d' && 'Last 7 Days Average'}
                    {projectionMode === 'last30d' && 'Last 30 Days Average'}
                  </span>
                  {matchupData.optimize_user_roster && (
                    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-800" title="Roster positions optimized for maximum active players">
                      ⚡ Optimized
                    </span>
                  )}
                </div>
                <RemainingDaysProjection
                  remaining_days_projection={matchupData.remaining_days_projection}
                  stat_categories={matchupData.stat_categories}
                  player_contributions={matchupData.player_contributions}
                  current_player_contributions={matchupData.current_player_contributions}
                  player_positions={matchupData.player_positions || {}}
                  week_start={matchupData.week_start}
                  week_end={matchupData.week_end}
                  title={`${matchupData.user_team.team_name} Remaining Games Projection`}
                  onPlayerClick={(playerId, playerName) => setSelectedPlayer({ id: playerId, name: playerName })}
                  sortField={projectionSortField}
                  sortDirection={projectionSortDirection}
                  onSort={handleProjectionSort}
                />
              </div>
            )}

            {/* Opponent Remaining Days Projection */}
            {matchupData.opponent_remaining_days_projection && Object.keys(matchupData.opponent_remaining_days_projection).length > 0 && (
              <div>
                <div className="text-sm text-gray-600 mb-2 px-6 flex items-center gap-2 flex-wrap">
                  <span>
                    <span className="font-medium">Projections based on: </span>
                    {projectionMode === 'season' && 'Season Average'}
                    {projectionMode === 'last3' && 'Last 3 Games Average'}
                    {projectionMode === 'last7' && 'Last 7 Games Average'}
                    {projectionMode === 'last7d' && 'Last 7 Days Average'}
                    {projectionMode === 'last30d' && 'Last 30 Days Average'}
                  </span>
                  {matchupData.optimize_opponent_roster && (
                    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-800" title="Roster positions optimized for maximum active players">
                      ⚡ Optimized
                    </span>
                  )}
                </div>
                <RemainingDaysProjection
                  remaining_days_projection={matchupData.opponent_remaining_days_projection}
                  stat_categories={matchupData.stat_categories}
                  player_contributions={matchupData.opponent_player_contributions}
                  current_player_contributions={matchupData.opponent_current_player_contributions || []}
                  player_positions={matchupData.opponent_player_positions || {}}
                  week_start={matchupData.week_start}
                  week_end={matchupData.week_end}
                  title={`${matchupData.opponent_team.team_name} Remaining Games Projection`}
                  onPlayerClick={(playerId, playerName) => setSelectedPlayer({ id: playerId, name: playerName })}
                  sortField={opponentProjectionSortField}
                  sortDirection={opponentProjectionSortDirection}
                  onSort={handleOpponentProjectionSort}
                />
              </div>
            )}
            </div>
          </div>
        )}
      </div>

      {/* Player Stats Modal */}
      {selectedPlayer && (
        <PlayerStatsModal
          playerId={selectedPlayer.id}
          playerName={selectedPlayer.name}
          isOpen={true}
          onClose={() => setSelectedPlayer(null)}
        />
      )}
    </Layout>
  );
}

