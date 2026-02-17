/**
 * Home page - Dashboard with top performers
 */

import { useState, useEffect, useRef } from 'react';
import { Layout } from '../components/Layout';
import { useLeague } from '../context/LeagueContext';
import { RefreshPanel } from '../components/RefreshPanel';
import { GameTypeSettings } from '../components/GameTypeSettings';
import { TopPerformersPanel } from '../components/TopPerformersPanel';
import { PlayerStatsModal } from '../components/PlayerStatsModal';
import { api } from '../services/api';
import type { GameBoxScore } from '../types/api';

// Get API URL from runtime config
const configUrl = window.APP_CONFIG?.API_URL;
const isPlaceholder = !configUrl || configUrl === '__API_URL__';
const API_BASE_URL = isPlaceholder 
  ? (import.meta.env.VITE_API_URL || 'https://localhost:8000')
  : configUrl;

export function Home() {
  const { defaultLeagueKey, isLoading } = useLeague();
  const [games, setGames] = useState<GameBoxScore[]>([]);
  const [displayDate, setDisplayDate] = useState<string>('');
  const [isLoadingGames, setIsLoadingGames] = useState(false);
  const [selectedPlayer, setSelectedPlayer] = useState<{ id: number; name: string } | null>(null);
  const [missingGamesCount, setMissingGamesCount] = useState<number>(0);
  const [isRefreshingMissing, setIsRefreshingMissing] = useState(false);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const [refreshTrigger, setRefreshTrigger] = useState(0); // Increment to trigger RefreshPanel sync
  const eventSourceRef = useRef<EventSource | null>(null);

  // Fetch missing games count after auth is ready
  useEffect(() => {
    if (isLoading) return;
    
    const fetchMissingGamesCount = async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/api/refresh/missing-games`, {
          credentials: 'include',
        });
        if (response.ok) {
          const data = await response.json();
          setMissingGamesCount(data.total_missing || 0);
        }
      } catch (err) {
        console.error('Failed to fetch missing games count:', err);
      }
    };
    
    fetchMissingGamesCount();
  }, [isLoading]);

  // Fetch the latest available box score data
  useEffect(() => {
    if (!defaultLeagueKey) return;

    const fetchLatestBoxScores = async () => {
      try {
        setIsLoadingGames(true);
        setRefreshError(null);
        const today = new Date().toISOString().split('T')[0];

        // First, try to get today's games
        const todayGames = await api.getGamesForDate(today);
        
        // Check if today has any games with actual box scores (not just scheduled)
        const todayWithBoxScores = todayGames.filter(g => !g.is_scheduled);

        if (todayWithBoxScores.length > 0) {
          // Today has box scores available
          setGames(todayWithBoxScores);
          setDisplayDate(today);
        } else {
          // No box scores today, find the most recent date with box scores
          await fetchMostRecentBoxScores(today);
        }
      } catch (err) {
        console.error('Failed to fetch box scores:', err);
        setGames([]);
        setDisplayDate('');
      } finally {
        setIsLoadingGames(false);
      }
    };

    const fetchMostRecentBoxScores = async (excludeDate: string) => {
      try {
        // Get all available dates
        const dates = await api.getBoxScoreDates();
        
        // Find the most recent date with games (before or equal to today)
        // that actually has box score data
        for (const dateInfo of dates) {
          if (dateInfo.date <= excludeDate || dateInfo.date === excludeDate) {
            const dateGames = await api.getGamesForDate(dateInfo.date);
            const gamesWithBoxScores = dateGames.filter(g => !g.is_scheduled);
            
            if (gamesWithBoxScores.length > 0) {
              setGames(gamesWithBoxScores);
              setDisplayDate(dateInfo.date);
              return;
            }
          }
        }
        
        // No box scores found at all
        setGames([]);
        setDisplayDate('');
      } catch (err) {
        console.error('Failed to fetch recent box scores:', err);
        setGames([]);
        setDisplayDate('');
      }
    };

    fetchLatestBoxScores();
  }, [defaultLeagueKey]);

  // Clean up EventSource on unmount
  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, []);

  const handlePlayerClick = (playerId: number, playerName: string) => {
    setSelectedPlayer({ id: playerId, name: playerName });
  };

  const handleRefreshMissing = () => {
    setIsRefreshingMissing(true);
    setRefreshError(null);

    // Build query parameters for smart refresh (no date range = fetch missing games)
    const params = new URLSearchParams({
      box_scores: 'true',
      waiver_cache: 'false',
      leagues: 'false',
      rebuild_player_indexes: 'false',
      player_rankings: 'false',
      nba_schedule: 'false',
      force_rebuild: 'false',
    });

    const url = `${API_BASE_URL}/api/refresh/start?${params.toString()}`;
    const eventSource = new EventSource(url, { withCredentials: true });
    eventSourceRef.current = eventSource;

    eventSource.onmessage = async (event) => {
      try {
        const data = JSON.parse(event.data);

        if (data.type === 'done') {
          eventSource.close();
          eventSourceRef.current = null;
          setIsRefreshingMissing(false);
          setMissingGamesCount(0); // Reset count after successful refresh
          setRefreshTrigger(prev => prev + 1); // Trigger RefreshPanel to sync
          
          // Refetch the latest box scores to update the display
          const today = new Date().toISOString().split('T')[0];
          const todayGames = await api.getGamesForDate(today);
          const todayWithBoxScores = todayGames.filter(g => !g.is_scheduled);
          
          if (todayWithBoxScores.length > 0) {
            setGames(todayWithBoxScores);
            setDisplayDate(today);
          } else {
            // Fetch the most recent available date
            const dates = await api.getBoxScoreDates();
            for (const dateInfo of dates) {
              if (dateInfo.date <= today) {
                const dateGames = await api.getGamesForDate(dateInfo.date);
                const gamesWithBoxScores = dateGames.filter(g => !g.is_scheduled);
                if (gamesWithBoxScores.length > 0) {
                  setGames(gamesWithBoxScores);
                  setDisplayDate(dateInfo.date);
                  break;
                }
              }
            }
          }
        } else if (data.type === 'error') {
          setRefreshError(data.message);
          setIsRefreshingMissing(false);
          eventSource.close();
          eventSourceRef.current = null;
        }
      } catch (err) {
        console.error('Failed to parse SSE event:', err);
      }
    };

    eventSource.onerror = () => {
      setRefreshError('Connection error. Please try again.');
      setIsRefreshingMissing(false);
      eventSource.close();
      eventSourceRef.current = null;
    };
  };

  const formatDisplayDate = (dateStr: string): string => {
    if (!dateStr) return '';
    const date = new Date(dateStr + 'T00:00:00');
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);
    
    const dateOnly = new Date(date);
    dateOnly.setHours(0, 0, 0, 0);
    
    if (dateOnly.getTime() === today.getTime()) {
      return 'Today';
    } else if (dateOnly.getTime() === yesterday.getTime()) {
      return 'Yesterday';
    }
    
    return date.toLocaleDateString('en-US', {
      weekday: 'short',
      month: 'short',
      day: 'numeric',
    });
  };

  return (
    <Layout>
      <div className="px-4 py-4 md:py-6 max-w-5xl mx-auto">
        <div className="text-center mb-6 md:mb-10">
          <h1 className="text-2xl md:text-4xl font-bold text-neutral-900 mb-2 md:mb-3">
            Welcome to Shams
          </h1>
          <p className="text-base md:text-xl text-gray-600">
            Fantasy Basketball Analysis & Tools
          </p>
        </div>

        {/* Top Performers Panel */}
        {isLoading ? (
          <div className="card bg-white p-6 mb-8">
            <div className="flex items-center justify-center py-8">
              <div className="text-center">
                <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-cyan-600 mb-3"></div>
                <p className="text-gray-600">Initializing...</p>
              </div>
            </div>
          </div>
        ) : defaultLeagueKey ? (
          <div className="mb-8">
            {/* Smart Refresh Banner - shows when there are missing games */}
            {missingGamesCount > 0 && !isLoadingGames && (
              <div className="mb-4 bg-blue-50 border border-blue-200 rounded-xl p-4">
                <div className="flex items-center justify-between flex-wrap gap-3">
                  <div className="flex items-center gap-3">
                    <svg className="w-5 h-5 text-blue-600 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
                    </svg>
                    <div>
                      <p className="text-blue-800 font-medium text-sm">{missingGamesCount} missing game{missingGamesCount !== 1 ? 's' : ''} available</p>
                      <p className="text-blue-700 text-xs mt-0.5">Box scores are available but haven't been fetched yet</p>
                    </div>
                  </div>
                  <button
                    onClick={handleRefreshMissing}
                    disabled={isRefreshingMissing}
                    className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                  >
                    {isRefreshingMissing ? (
                      <>
                        <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                        Refreshing...
                      </>
                    ) : (
                      <>
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                        </svg>
                        Smart Refresh
                      </>
                    )}
                  </button>
                </div>
                {refreshError && (
                  <p className="text-red-600 text-xs mt-2">{refreshError}</p>
                )}
              </div>
            )}

            {isLoadingGames ? (
              <div className="card bg-white p-6">
                <div className="flex items-center justify-center py-8">
                  <div className="text-center">
                    <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-cyan-600 mb-3"></div>
                    <p className="text-gray-600">Loading top performers...</p>
                  </div>
                </div>
              </div>
            ) : games.length > 0 ? (
              <div>
                {/* Date indicator */}
                {displayDate && (
                  <div className="flex items-center justify-between mb-3">
                    <p className="text-sm text-gray-600">
                      Showing performances from <span className="font-semibold text-gray-900">{formatDisplayDate(displayDate)}</span>
                    </p>
                  </div>
                )}
                <TopPerformersPanel games={games} onPlayerClick={handlePlayerClick} />
              </div>
            ) : (
              <div className="card bg-white p-6">
                <h2 className="text-xl font-bold text-gray-900 mb-2">Top Performers</h2>
                <p className="text-gray-600">No box scores available. Use the refresh panel below to fetch game data.</p>
              </div>
            )}
          </div>
        ) : (
          <div className="card bg-white p-6 mb-8">
            <div className="text-center py-8">
              <svg className="mx-auto h-12 w-12 text-gray-400 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <h2 className="text-xl font-bold text-gray-900 mb-2">Select a League</h2>
              <p className="text-gray-600">Choose a league from the dropdown in the navigation bar to get started.</p>
            </div>
          </div>
        )}

        {/* Data Refresh Panel */}
        <RefreshPanel leagueKey={defaultLeagueKey} refreshTrigger={refreshTrigger} />

        {/* Game Type Settings */}
        <GameTypeSettings leagueKey={defaultLeagueKey} />
      </div>

      {/* Player Stats Modal */}
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
