/**
 * Refresh Panel Component
 * Allows users to refresh different data sources with progress tracking
 */

import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ProgressDisplay } from './ProgressDisplay';
import { MissingGamesTable } from './MissingGamesTable';
import { useLeague } from '../context/LeagueContext';
import type { RefreshProgressEvent } from '../types/api';

// Get API URL from runtime config (set at container startup) or build-time env var
// In Docker production, __API_URL__ placeholder is replaced at container startup
// In local dev, the placeholder won't be replaced so we fall back to env var or default
const configUrl = window.APP_CONFIG?.API_URL;
const isPlaceholder = !configUrl || configUrl === '__API_URL__';
const API_BASE_URL = isPlaceholder 
  ? (import.meta.env.VITE_API_URL || 'https://localhost:8000')
  : configUrl;

interface RefreshPanelProps {
  leagueKey?: string | null;
  refreshTrigger?: number; // Increment to trigger a refetch of cache status and missing games
}

interface CacheStatus {
  has_cache: boolean;
  last_date?: string;
  games_count: number;
  season: string;
}

interface SeasonInfo {
  season: string;
  season_start_date: string;
  current_date: string;
  available_seasons: string[];
  cached_season: string | null;
}

export function RefreshPanel({ leagueKey, refreshTrigger }: RefreshPanelProps) {
  const navigate = useNavigate();
  const { isLoading: isLeagueLoading } = useLeague();
  const [isExpanded, setIsExpanded] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [completedSteps, setCompletedSteps] = useState<string[]>([]);
  const [currentStep, setCurrentStep] = useState<string | null>(null);
  const [isComplete, setIsComplete] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<any>(null);
  const [cacheStatus, setCacheStatus] = useState<CacheStatus | null>(null);
  const [seasonInfo, setSeasonInfo] = useState<SeasonInfo | null>(null);
  const [missingGamesCount, setMissingGamesCount] = useState<number>(0);
  const [loadingMissing, setLoadingMissing] = useState<boolean>(true);
  const [showMissingGames, setShowMissingGames] = useState(false);
  
  // Refresh options
  const [refreshBoxScores, setRefreshBoxScores] = useState(true);
  const [refreshWaiverCache, setRefreshWaiverCache] = useState(false);
  const [refreshLeagues, setRefreshLeagues] = useState(false);
  const [refreshPlayerIndex, setRefreshPlayerIndex] = useState(false);
  const [refreshNbaSchedule, setRefreshNbaSchedule] = useState(false);
  const [forceRebuild, setForceRebuild] = useState(false);
  
  // Date range for box scores
  const [startDate, setStartDate] = useState<string>('');
  const [endDate, setEndDate] = useState<string>('');
  
  // Season selector
  const [selectedSeason, setSelectedSeason] = useState<string>('');
  const [showSeasonConfirm, setShowSeasonConfirm] = useState(false);
  const [pendingSeasonChange, setPendingSeasonChange] = useState<string | null>(null);
  
  const eventSourceRef = useRef<EventSource | null>(null);
  
  // Fetch cache status, season info, and missing games once league context is ready
  // Wait for isLeagueLoading to be false to ensure session cookie is set
  // Also refetch when refreshTrigger changes (e.g., after Smart Refresh in Home page)
  useEffect(() => {
    if (isLeagueLoading) {
      return; // Wait for authentication to complete
    }
    fetchCacheStatus(refreshTrigger !== undefined && refreshTrigger > 0);
    fetchSeasonInfo();
    fetchMissingGamesCount(refreshTrigger !== undefined && refreshTrigger > 0);
  }, [isLeagueLoading, refreshTrigger]);
  
  // Clean up EventSource on unmount
  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, []);
  
  const fetchCacheStatus = async (bustCache = false) => {
    try {
      const url = new URL(`${API_BASE_URL}/api/config/cache-status`);
      if (bustCache) {
        url.searchParams.set('_t', Date.now().toString());
      }
      const response = await fetch(url.toString(), {
        credentials: 'include',
      });
      if (response.ok) {
        const text = await response.text();
        if (text) {
          const data = JSON.parse(text);
          setCacheStatus(data);
        }
      } else {
        console.error(`Cache status request failed with status: ${response.status}`);
      }
    } catch (err) {
      // Silently fail - cache status is optional
      console.error('Failed to fetch cache status:', err);
    }
  };
  
  const fetchSeasonInfo = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/config/season-info`, {
        credentials: 'include',
      });
      if (response.ok) {
        const text = await response.text();
        if (text) {
          const data = JSON.parse(text);
          setSeasonInfo(data);
          // Set selected season to cached season if available, otherwise detected season
          if (!selectedSeason) {
            setSelectedSeason(data.cached_season || data.season);
          }
        }
      } else {
        console.error(`Season info request failed with status: ${response.status}`);
      }
    } catch (err) {
      // Silently fail - will use fallback dates
      console.error('Failed to fetch season info:', err);
    }
  };
  
  const fetchMissingGamesCount = async (bustCache = false) => {
    setLoadingMissing(true);
    try {
      const url = new URL(`${API_BASE_URL}/api/refresh/missing-games`);
      if (bustCache) {
        url.searchParams.set('_t', Date.now().toString());
      }
      const response = await fetch(url.toString(), {
        credentials: 'include',
      });
      if (response.ok) {
        const text = await response.text();
        if (text) {
          const data = JSON.parse(text);
          setMissingGamesCount(data.total_missing || 0);
        }
      } else if (response.status === 401) {
        // User not authenticated - expected if not logged in
        console.debug('Missing games requires authentication');
      } else {
        console.error(`Missing games request failed with status: ${response.status}`);
      }
    } catch (err) {
      // Silently fail - missing games count is optional
      console.error('Failed to fetch missing games count:', err);
    } finally {
      setLoadingMissing(false);
    }
  };
  
  const handleSeasonChange = (newSeason: string) => {
    const currentCachedSeason = seasonInfo?.cached_season || cacheStatus?.season;
    
    // If there's a cache and the season is different, show confirmation
    if (currentCachedSeason && newSeason !== currentCachedSeason && cacheStatus?.has_cache) {
      setPendingSeasonChange(newSeason);
      setShowSeasonConfirm(true);
    } else {
      setSelectedSeason(newSeason);
    }
  };
  
  const confirmSeasonChange = () => {
    if (pendingSeasonChange) {
      setSelectedSeason(pendingSeasonChange);
      setPendingSeasonChange(null);
    }
    setShowSeasonConfirm(false);
  };
  
  const cancelSeasonChange = () => {
    setPendingSeasonChange(null);
    setShowSeasonConfirm(false);
  };

  const handleRefresh = () => {
    // Validate that at least one option is selected
    if (!refreshBoxScores && !refreshWaiverCache && !refreshLeagues && !refreshPlayerIndex && !refreshNbaSchedule) {
      setError('Please select at least one data source to refresh');
      return;
    }
    
    // Validate league key for waiver cache only (player index refreshes all leagues)
    if (refreshWaiverCache && !leagueKey) {
      setError('League key required for waiver cache refresh. Please select a league first.');
      return;
    }
    
    // Reset state
    setIsRefreshing(true);
    setCompletedSteps([]);
    setCurrentStep(null);
    setIsComplete(false);
    setError(null);
    setSummary(null);
    
    // Build query parameters
    // Player Index combines both rebuild_player_indexes and player_rankings
    const params = new URLSearchParams({
      box_scores: refreshBoxScores.toString(),
      waiver_cache: refreshWaiverCache.toString(),
      leagues: refreshLeagues.toString(),
      rebuild_player_indexes: refreshPlayerIndex.toString(),
      player_rankings: refreshPlayerIndex.toString(),
      nba_schedule: refreshNbaSchedule.toString(),
      force_rebuild: forceRebuild.toString(),
    });
    
    if (leagueKey && (refreshWaiverCache || refreshPlayerIndex)) {
      params.append('league_key', leagueKey);
    }
    
    if (startDate) {
      params.append('start_date', startDate);
      console.log('Adding start_date:', startDate);
    }
    
    if (endDate) {
      params.append('end_date', endDate);
      console.log('Adding end_date:', endDate);
    }
    
    // Add season parameter if selected (triggers rebuild if different from cached)
    if (selectedSeason) {
      params.append('season', selectedSeason);
      console.log('Adding season:', selectedSeason);
    }
    
    // Create EventSource for SSE
    const url = `${API_BASE_URL}/api/refresh/start?${params.toString()}`;
    console.log('Refresh URL:', url);
    const eventSource = new EventSource(url, { withCredentials: true });
    eventSourceRef.current = eventSource;
    
    eventSource.onmessage = (event) => {
      try {
        const data: RefreshProgressEvent = JSON.parse(event.data);
        
        switch (data.type) {
          case 'status':
            setCurrentStep(data.message);
            break;
            
          case 'complete':
            setCompletedSteps(prev => [...prev, data.message]);
            setCurrentStep(null);
            break;
            
          case 'done':
            setIsComplete(true);
            setIsRefreshing(false);
            setCurrentStep(data.message);
            setSummary(data.data);
            eventSource.close();
            eventSourceRef.current = null;
            // Refetch cache status and missing games after refresh completes
            // Use cache busting to ensure fresh data from server
            fetchCacheStatus(true);
            fetchMissingGamesCount(true);
            break;
            
          case 'error':
            setError(data.message);
            setIsRefreshing(false);
            setIsComplete(false);
            eventSource.close();
            eventSourceRef.current = null;
            break;
        }
      } catch (err) {
        console.error('Failed to parse SSE event:', err);
      }
    };
    
    eventSource.onerror = (err) => {
      console.error('SSE error:', err);
      setError('Connection error. Please try again.');
      setIsRefreshing(false);
      setIsComplete(false);
      eventSource.close();
      eventSourceRef.current = null;
    };
  };
  
  const formatSummary = (data: any) => {
    const parts: string[] = [];
    
    if (data.box_scores) {
      const bs = data.box_scores;
      parts.push(`Box Scores: ${bs.games_fetched} games, ${bs.players_updated} players`);
    }
    
    // Combine player_indexes and player_rankings into one summary
    const indexParts: string[] = [];
    if (data.player_indexes) {
      const pi = data.player_indexes;
      indexParts.push(`${pi.players_updated} NBA players indexed`);
    }
    if (data.player_rankings) {
      const pr = data.player_rankings;
      if (pr.error) {
        indexParts.push(`Rankings error: ${pr.error}`);
      } else {
        indexParts.push(`${pr.players_fetched} Yahoo players ranked`);
      }
    }
    if (indexParts.length > 0) {
      parts.push(`Player Index: ${indexParts.join(', ')}`);
    }
    
    if (data.waiver_cache) {
      parts.push('Waiver cache cleared');
    }
    
    if (data.leagues) {
      parts.push('Leagues refreshed');
    }
    
    if (data.nba_schedule) {
      const ns = data.nba_schedule;
      parts.push(`NBA Schedule: ${ns.teams_cached} teams cached`);
    }
    
    return parts.join(' • ');
  };
  
  return (
    <div className="card p-4 md:p-6 mb-6 md:mb-8">
      {/* Header */}
      <div className="space-y-3 md:space-y-0 md:flex md:items-start md:justify-between mb-4">
        <div className="flex-1">
          <h2 className="text-xl font-bold text-gray-900">Data Refresh</h2>
          <p className="text-xs md:text-sm text-gray-600 mt-1">
            Update your local cache with the latest data
          </p>
          {cacheStatus?.has_cache && cacheStatus.last_date && (
            <p className="text-xs text-gray-500 mt-2">
              Cache: {cacheStatus.games_count} games through {cacheStatus.last_date} (Season: {cacheStatus.season})
              <span className="block md:inline md:ml-2 font-medium mt-1 md:mt-0">
                {loadingMissing ? (
                  <span className="text-gray-500 inline-flex items-center gap-1.5">
                    <svg className="animate-spin h-3 w-3" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    <span>Checking for updates...</span>
                  </span>
                ) : missingGamesCount > 0 ? (
                  <span className="text-blue-600">• {missingGamesCount} missing</span>
                ) : (
                  <span className="text-green-600">• All games cached</span>
                )}
              </span>
            </p>
          )}
        </div>
        <div className="flex items-center gap-2 justify-end md:justify-start">
          <button
            onClick={() => navigate('/cache-debug')}
            className="flex-1 md:flex-none px-3 md:px-4 py-2 text-xs md:text-sm text-blue-600 hover:bg-blue-50 rounded-lg transition-colors flex items-center justify-center gap-2 border border-blue-200"
          >
            <svg className="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            <span className="hidden md:inline">View Cache</span>
            <span className="md:hidden">Cache</span>
          </button>
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="px-3 md:px-4 py-2 text-xs md:text-sm text-gray-600 hover:bg-neutral-100 rounded-lg transition-colors flex items-center gap-2"
          >
            {isExpanded ? 'Hide' : 'Show'}
            <svg 
              className={`w-4 h-4 transition-transform ${isExpanded ? 'rotate-180' : ''}`}
              fill="none" 
              stroke="currentColor" 
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </button>
        </div>
      </div>
      
      {/* Expandable content */}
      {isExpanded && (
        <div className="space-y-4 md:space-y-6">
          {/* Season Selector */}
          {seasonInfo?.available_seasons && seasonInfo.available_seasons.length > 0 && (
            <div className="bg-gray-50 rounded-xl p-4 border border-gray-200">
              <div className="flex flex-col md:flex-row md:items-center gap-3">
                <div className="flex-1">
                  <label className="block text-xs md:text-sm font-medium text-gray-700 mb-1">
                    NBA Season
                  </label>
                  <select
                    value={selectedSeason}
                    onChange={(e) => handleSeasonChange(e.target.value)}
                    disabled={isRefreshing}
                    className="w-full md:w-48 px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50 disabled:cursor-not-allowed bg-white"
                  >
                    {seasonInfo.available_seasons.map((season) => (
                      <option key={season} value={season}>
                        {season}
                        {season === seasonInfo.season && ' (current)'}
                        {season === seasonInfo.cached_season && season !== seasonInfo.season && ' (cached)'}
                      </option>
                    ))}
                  </select>
                </div>
                {selectedSeason && cacheStatus?.season && selectedSeason !== cacheStatus.season && (
                  <div className="flex items-center gap-2 text-amber-700 bg-amber-50 px-3 py-2 rounded-lg">
                    <svg className="w-4 h-4 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                    </svg>
                    <span className="text-xs">
                      Changing season will clear cache and rebuild
                    </span>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Options */}
          <div className="space-y-3">
            <p className="text-xs md:text-sm font-medium text-gray-700 mb-3">Select data to refresh:</p>
            
            <div>
              <label className="flex items-start gap-3 cursor-pointer group">
                <input
                  type="checkbox"
                  checked={refreshBoxScores}
                  onChange={(e) => setRefreshBoxScores(e.target.checked)}
                  disabled={isRefreshing}
                  className="mt-0.5 md:mt-1 h-4 w-4 text-blue-600 rounded border-gray-300 focus:ring-blue-500 disabled:opacity-50 flex-shrink-0"
                />
                <div className="flex-1">
                  <div className="text-xs md:text-sm font-medium text-gray-900 group-hover:text-gray-700">
                    Box Scores (NBA Game Data)
                  </div>
                  <div className="text-xs text-gray-500 mt-0.5">
                    Fetches latest NBA games and updates player statistics
                  </div>
                </div>
              </label>
              
              {/* Box Scores Sub-options */}
              {refreshBoxScores && (
                <div className="ml-5 md:ml-7 mt-3 space-y-3 pl-3 md:pl-4 border-l-2 border-gray-200">
                  {/* Date Range */}
                  <div>
                    <p className="text-xs font-medium text-gray-700 mb-2">
                      Optional: Specify date range (leave empty for smart refresh)
                    </p>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      <div>
                        <label className="block text-xs text-gray-600 mb-1">
                          Start Date
                        </label>
                        <input
                          type="date"
                          value={startDate}
                          onChange={(e) => setStartDate(e.target.value)}
                          disabled={isRefreshing || forceRebuild}
                          min={seasonInfo?.season_start_date || undefined}
                          max={seasonInfo?.current_date || undefined}
                          className="w-full px-3 py-2 text-xs md:text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50 disabled:cursor-not-allowed"
                        />
                      </div>
                      <div>
                        <label className="block text-xs text-gray-600 mb-1">
                          End Date
                        </label>
                        <input
                          type="date"
                          value={endDate}
                          onChange={(e) => setEndDate(e.target.value)}
                          disabled={isRefreshing || forceRebuild}
                          min={startDate || seasonInfo?.season_start_date || undefined}
                          max={seasonInfo?.current_date || undefined}
                          className="w-full px-3 py-2 text-xs md:text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50 disabled:cursor-not-allowed"
                        />
                      </div>
                    </div>
                    {(startDate || endDate) && (
                      <button
                        onClick={() => {
                          setStartDate('');
                          setEndDate('');
                        }}
                        disabled={isRefreshing}
                        className="mt-2 text-xs text-blue-600 hover:text-blue-800 disabled:opacity-50"
                      >
                        Clear dates (use smart refresh)
                      </button>
                    )}
                    {seasonInfo && (
                      <p className="text-xs text-gray-500 mt-2">
                        Available range: {seasonInfo.season_start_date} to {seasonInfo.current_date}
                      </p>
                    )}
                  </div>
                  
                  {/* Force Rebuild */}
                  <div>
                    <label className="flex items-start gap-3 cursor-pointer group">
                      <input
                        type="checkbox"
                        checked={forceRebuild}
                        onChange={(e) => setForceRebuild(e.target.checked)}
                        disabled={isRefreshing}
                        className="mt-0.5 md:mt-1 h-4 w-4 text-amber-600 rounded border-gray-300 focus:ring-amber-500 disabled:opacity-50 flex-shrink-0"
                      />
                      <div className="flex-1">
                        <div className="text-xs md:text-sm font-medium text-amber-900 group-hover:text-amber-700">
                          Force Full Rebuild
                        </div>
                        <div className="text-xs text-amber-700 mt-0.5">
                          Clear cache and rebuild from scratch (takes longer but ensures fresh data)
                        </div>
                      </div>
                    </label>
                  </div>
                </div>
              )}
            </div>
            
            <label className="flex items-start gap-3 cursor-pointer group">
              <input
                type="checkbox"
                checked={refreshPlayerIndex}
                onChange={(e) => setRefreshPlayerIndex(e.target.checked)}
                disabled={isRefreshing}
                className="mt-0.5 md:mt-1 h-4 w-4 text-blue-600 rounded border-gray-300 focus:ring-blue-500 disabled:opacity-50 flex-shrink-0"
              />
              <div className="flex-1">
                <div className="text-xs md:text-sm font-medium text-gray-900 group-hover:text-gray-700">
                  Player Index (Yahoo Fantasy)
                </div>
                <div className="text-xs text-gray-500 mt-0.5">
                  Fetches Yahoo rankings for all leagues and rebuilds player game indexes
                </div>
              </div>
            </label>
            
            <label className="flex items-start gap-3 cursor-pointer group">
              <input
                type="checkbox"
                checked={refreshWaiverCache}
                onChange={(e) => setRefreshWaiverCache(e.target.checked)}
                disabled={isRefreshing}
                className="mt-0.5 md:mt-1 h-4 w-4 text-blue-600 rounded border-gray-300 focus:ring-blue-500 disabled:opacity-50 flex-shrink-0"
              />
              <div className="flex-1">
                <div className="text-xs md:text-sm font-medium text-gray-900 group-hover:text-gray-700">
                  Waiver Cache
                </div>
                <div className="text-xs text-gray-500 mt-0.5">
                  Clears cached waiver wire data to fetch fresh Yahoo data
                  {!leagueKey && <span className="text-amber-600"> (requires league selection)</span>}
                </div>
              </div>
            </label>
            
            <label className="flex items-start gap-3 cursor-pointer group">
              <input
                type="checkbox"
                checked={refreshLeagues}
                onChange={(e) => setRefreshLeagues(e.target.checked)}
                disabled={isRefreshing}
                className="mt-0.5 md:mt-1 h-4 w-4 text-blue-600 rounded border-gray-300 focus:ring-blue-500 disabled:opacity-50 flex-shrink-0"
              />
              <div className="flex-1">
                <div className="text-xs md:text-sm font-medium text-gray-900 group-hover:text-gray-700">
                  Leagues
                </div>
                <div className="text-xs text-gray-500 mt-0.5">
                  Refreshes your Yahoo Fantasy leagues list
                </div>
              </div>
            </label>
            
            <label className="flex items-start gap-3 cursor-pointer group">
              <input
                type="checkbox"
                checked={refreshNbaSchedule}
                onChange={(e) => setRefreshNbaSchedule(e.target.checked)}
                disabled={isRefreshing}
                className="mt-0.5 md:mt-1 h-4 w-4 text-blue-600 rounded border-gray-300 focus:ring-blue-500 disabled:opacity-50 flex-shrink-0"
              />
              <div className="flex-1">
                <div className="text-xs md:text-sm font-medium text-gray-900 group-hover:text-gray-700">
                  NBA Schedule
                </div>
                <div className="text-xs text-gray-500 mt-0.5">
                  Updates NBA game schedule (useful when schedule changes due to NBA Cup or postponements)
                </div>
              </div>
            </label>
          </div>
          
          {/* Refresh button */}
          <div>
            <button
              onClick={handleRefresh}
              disabled={isRefreshing}
              className={`w-full md:w-auto px-6 py-2.5 rounded-xl font-medium transition-all text-sm md:text-base ${
                isRefreshing
                  ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                  : 'bg-neutral-900 text-white hover:bg-neutral-800 hover:shadow-lg'
              }`}
            >
              {isRefreshing ? 'Refreshing...' : 'Start Refresh'}
            </button>
          </div>
          
          {/* Error display */}
          {error && (
            <div className="bg-red-50 border border-red-200 rounded-xl p-4">
              <div className="flex items-start gap-2">
                <svg className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                </svg>
                <div>
                  <p className="text-sm font-semibold text-red-800">Error</p>
                  <p className="text-sm text-red-700 mt-0.5">{error}</p>
                </div>
              </div>
            </div>
          )}
          
          {/* Progress display */}
          {(isRefreshing || isComplete || completedSteps.length > 0) && !error && (
            <div className="bg-blue-50 border border-blue-200 rounded-xl p-4">
              <ProgressDisplay
                completedSteps={completedSteps}
                currentStep={currentStep}
                isComplete={isComplete}
              />
              
              {/* Summary */}
              {isComplete && summary && (
                <div className="mt-4 pt-4 border-t border-blue-200">
                  <p className="text-sm text-gray-700">
                    {formatSummary(summary)}
                  </p>
                </div>
              )}
            </div>
          )}
        </div>
      )}
      
      {/* Missing Games Section */}
      {missingGamesCount > 0 && (
        <div className="mt-4 pt-4 border-t border-gray-200">
          <button
            onClick={() => setShowMissingGames(!showMissingGames)}
            className="flex items-center justify-between w-full text-left"
          >
            <div className="flex items-center gap-2 flex-wrap">
              <svg className="w-4 md:w-5 h-4 md:h-5 text-amber-500 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
              </svg>
              <span className="text-base md:text-lg font-semibold text-gray-900">
                Missing Games
              </span>
              {missingGamesCount > 0 && (
                <span className="px-2 py-0.5 text-xs font-medium bg-blue-100 text-blue-800 rounded-full">
                  {missingGamesCount} missing
                </span>
              )}
            </div>
            <svg 
              className={`w-5 h-5 text-gray-400 transition-transform ${showMissingGames ? 'rotate-180' : ''}`}
              fill="none" 
              stroke="currentColor" 
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </button>
          
          {showMissingGames && (
            <div className="mt-4">
              <MissingGamesTable onRefresh={() => {
                fetchMissingGamesCount(true);
                fetchCacheStatus(true);
              }} />
            </div>
          )}
        </div>
      )}
      
      {/* Season Change Confirmation Modal */}
      {showSeasonConfirm && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl shadow-xl max-w-md w-full p-6">
            <div className="flex items-start gap-3 mb-4">
              <div className="flex-shrink-0 w-10 h-10 rounded-full bg-amber-100 flex items-center justify-center">
                <svg className="w-5 h-5 text-amber-600" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                </svg>
              </div>
              <div>
                <h3 className="text-lg font-semibold text-gray-900">Change Season?</h3>
                <p className="text-sm text-gray-600 mt-1">
                  You're about to change from <strong>{cacheStatus?.season || seasonInfo?.cached_season}</strong> to <strong>{pendingSeasonChange}</strong>.
                </p>
              </div>
            </div>
            
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 mb-5">
              <p className="text-sm text-amber-800">
                <strong>Warning:</strong> This will delete your existing cache ({cacheStatus?.games_count || 0} games) and rebuild from scratch. This may take several minutes.
              </p>
            </div>
            
            <div className="flex gap-3">
              <button
                onClick={cancelSeasonChange}
                className="flex-1 px-4 py-2.5 text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-xl transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={confirmSeasonChange}
                className="flex-1 px-4 py-2.5 text-sm font-medium text-white bg-amber-600 hover:bg-amber-700 rounded-xl transition-colors"
              >
                Change Season
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

