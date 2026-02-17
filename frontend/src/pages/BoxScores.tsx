/**
 * Box Scores page - displays NBA game box scores by date
 */

import { useState, useEffect } from 'react';
import { Layout } from '../components/Layout';
import { WeeklyCalendar } from '../components/WeeklyCalendar';
import { GameCard } from '../components/GameCard';
import { PlayerStatsModal } from '../components/PlayerStatsModal';
import { TopPerformersPanel } from '../components/TopPerformersPanel';
import { useLeague } from '../context/LeagueContext';
import { api } from '../services/api';
import type { BoxScoreDate, GameBoxScore } from '../types/api';

export function BoxScores() {
  const { isLoading: isLeagueLoading } = useLeague();
  const [selectedDate, setSelectedDate] = useState<string>('');
  const [allDates, setAllDates] = useState<BoxScoreDate[]>([]);
  const [games, setGames] = useState<GameBoxScore[]>([]);
  const [isLoadingDates, setIsLoadingDates] = useState(true);
  const [isLoadingGames, setIsLoadingGames] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedPlayer, setSelectedPlayer] = useState<{ id: number; name: string } | null>(null);

  // Fetch all available dates on mount (but wait for session to initialize)
  useEffect(() => {
    // Don't fetch until LeagueContext has finished initializing the session
    if (isLeagueLoading) return;

    const fetchDates = async () => {
      try {
        setIsLoadingDates(true);
        setError(null);
        
        // Get all dates with games
        const dates = await api.getBoxScoreDates();
        setAllDates(dates);
        
        // Always default to today's date
        const today = new Date().toISOString().split('T')[0];
        setSelectedDate(today);
        
        // If no dates at all, show error message
        if (dates.length === 0) {
          setError('No cached box scores found. Please refresh the cache from the home page.');
        }
      } catch (err: any) {
        console.error('Failed to fetch dates:', err);
        setError(err.response?.data?.detail || 'Failed to load box score dates');
      } finally {
        setIsLoadingDates(false);
      }
    };

    fetchDates();
  }, [isLeagueLoading]);

  // Fetch games when selected date changes
  useEffect(() => {
    if (!selectedDate) return;

    const fetchGames = async () => {
      try {
        setIsLoadingGames(true);
        setError(null);
        const gamesData = await api.getGamesForDate(selectedDate);
        setGames(gamesData);
      } catch (err: any) {
        console.error('Failed to fetch games:', err);
        setError(err.response?.data?.detail || 'Failed to load games');
        setGames([]);
      } finally {
        setIsLoadingGames(false);
      }
    };

    fetchGames();
  }, [selectedDate]);

  const handleDateSelect = (date: string) => {
    setSelectedDate(date);
  };

  const handlePlayerClick = (playerId: number, playerName: string) => {
    setSelectedPlayer({ id: playerId, name: playerName });
  };

  const formatDate = (dateStr: string): string => {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', {
      weekday: 'long',
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    });
  };

  return (
    <Layout>
      <div className="px-4 py-4 md:py-6 max-w-7xl mx-auto">
        {/* Page header */}
        <div className="mb-4 md:mb-6">
          <h1 className="text-2xl md:text-3xl font-bold text-neutral-900 mb-1 md:mb-2">
            NBA Box Scores
          </h1>
          <p className="text-sm md:text-base text-gray-600">
            View detailed game statistics and player box scores
          </p>
        </div>

        {/* Loading state for initial dates fetch */}
        {(isLoadingDates || isLeagueLoading) && (
          <div className="flex items-center justify-center py-8 md:py-12">
            <div className="text-center">
              <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-neutral-900 mb-3"></div>
              <p className="text-gray-600 text-sm md:text-base">
                {isLeagueLoading ? 'Initializing session...' : 'Loading available dates...'}
              </p>
            </div>
          </div>
        )}

        {/* Error state */}
        {error && !isLoadingDates && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-4 md:mb-6">
            <div className="flex items-start">
              <svg
                className="w-5 h-5 text-red-600 mt-0.5 mr-3 flex-shrink-0"
                fill="currentColor"
                viewBox="0 0 20 20"
              >
                <path
                  fillRule="evenodd"
                  d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                  clipRule="evenodd"
                />
              </svg>
              <div>
                <h3 className="text-xs md:text-sm font-medium text-red-800">Error</h3>
                <p className="text-xs md:text-sm text-red-700 mt-1">{error}</p>
              </div>
            </div>
          </div>
        )}

        {/* Calendar and games display */}
        {!isLoadingDates && allDates.length > 0 && (
          <>
            {/* Weekly calendar */}
            <WeeklyCalendar
              selectedDate={selectedDate}
              onDateSelect={handleDateSelect}
              allDates={allDates}
            />

            {/* Selected date display */}
            <div className="mb-4">
              <h2 className="text-xl font-semibold text-gray-900">
                {formatDate(selectedDate)}
              </h2>
              <p className="text-sm text-gray-600 mt-1">
                {games.length} {games.length === 1 ? 'game' : 'games'}
              </p>
            </div>

            {/* Loading state for games */}
            {isLoadingGames && (
              <div className="flex items-center justify-center py-12">
                <div className="text-center">
                  <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-neutral-900 mb-3"></div>
                  <p className="text-gray-600">Loading games...</p>
                </div>
              </div>
            )}

            {/* Games list with Top Performers Panel */}
            {!isLoadingGames && games.length > 0 && (
              <div className="flex flex-col lg:flex-row gap-4">
                {/* Left: Box Scores */}
                <div className="flex-1 lg:w-2/3">
                  <div className="space-y-4">
                    {games.map((game) => (
                      <GameCard key={game.game_id} game={game} onPlayerClick={handlePlayerClick} />
                    ))}
                  </div>
                </div>

                {/* Right: Top Performers */}
                <div className="lg:w-1/3">
                  <TopPerformersPanel games={games} onPlayerClick={handlePlayerClick} compact />
                </div>
              </div>
            )}

            {/* Empty state - no games for selected date */}
            {!isLoadingGames && games.length === 0 && !error && (
              <div className="text-center py-12">
                <svg
                  className="mx-auto h-12 w-12 text-gray-400 mb-3"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"
                  />
                </svg>
                <p className="text-gray-600">No games found for this date</p>
              </div>
            )}
          </>
        )}
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

