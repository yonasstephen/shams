/**
 * Missing Games Table Component
 * Displays games that are missing from the box score cache (detected by comparing schedule vs cache)
 * with retry functionality
 */

import { useState, useEffect, useRef } from 'react';

// Get API URL from runtime config (set at container startup) or build-time env var
// In Docker production, __API_URL__ placeholder is replaced at container startup
// In local dev, the placeholder won't be replaced so we fall back to env var or default
const configUrl = window.APP_CONFIG?.API_URL;
const isPlaceholder = !configUrl || configUrl === '__API_URL__';
const API_BASE_URL = isPlaceholder 
  ? (import.meta.env.VITE_API_URL || 'https://localhost:8000')
  : configUrl;

interface MissingGame {
  game_id: string;
  home_team: string;
  away_team: string;
  home_team_tricode: string;
  away_team_tricode: string;
  game_datetime: string;
}

interface MissingDateInfo {
  expected: number;
  cached: number;
  missing: MissingGame[];
  missing_count: number;
}

interface RetryProgressEvent {
  type: 'status' | 'progress' | 'game_complete' | 'done' | 'error';
  message?: string;
  current?: number;
  total?: number;
  game_id?: string;
  matchup?: string;
  date?: string;
  status?: 'success' | 'failed';
  reason?: string;
  data?: {
    games_retried: number;
    games_successful: number;
    games_still_missing: number;
  };
}

interface MissingGamesTableProps {
  onRefresh?: () => void;
}

export function MissingGamesTable({ onRefresh }: MissingGamesTableProps) {
  // Missing games state
  const [missingByDate, setMissingByDate] = useState<Record<string, MissingDateInfo>>({});
  const [totalMissing, setTotalMissing] = useState(0);
  
  // Loading states
  const [loading, setLoading] = useState(false);
  
  // Retry states
  const [retrying, setRetrying] = useState(false);
  const [retryProgress, setRetryProgress] = useState<{current: number; total: number; message: string} | null>(null);
  const [retryResults, setRetryResults] = useState<{game_id: string; status: 'success' | 'failed'; message: string}[]>([]);
  const [retryingGameId, setRetryingGameId] = useState<string | null>(null);
  
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  
  const eventSourceRef = useRef<EventSource | null>(null);

  const fetchMissingGames = async () => {
    setLoading(true);
    setError(null);
    
    try {
      const response = await fetch(`${API_BASE_URL}/api/refresh/missing-games`, {
        credentials: 'include',
      });
      
      if (!response.ok) {
        throw new Error('Failed to fetch missing games');
      }
      
      const data = await response.json();
      setMissingByDate(data.by_date || {});
      setTotalMissing(data.total_missing || 0);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch missing games');
    } finally {
      setLoading(false);
    }
  };

  const retryGame = async (gameId: string) => {
    setRetryingGameId(gameId);
    setError(null);
    setSuccessMessage(null);
    
    // Create EventSource for SSE with single game
    const url = `${API_BASE_URL}/api/refresh/retry-missing-stream?game_ids=${gameId}`;
    const eventSource = new EventSource(url, { withCredentials: true });
    
    eventSource.onmessage = (event) => {
      try {
        const data: RetryProgressEvent = JSON.parse(event.data);
        
        if (data.type === 'game_complete') {
          if (data.status === 'success') {
            setSuccessMessage(`Successfully fetched game ${gameId}`);
          } else {
            setError(`Game ${gameId}: ${data.message || 'Failed to fetch'}`);
          }
        } else if (data.type === 'done') {
          eventSource.close();
          setRetryingGameId(null);
          // Refresh the list
          fetchMissingGames();
          // Notify parent component
          if (onRefresh) {
            onRefresh();
          }
        } else if (data.type === 'error') {
          setError(data.message || 'Unknown error occurred');
          eventSource.close();
          setRetryingGameId(null);
        }
      } catch (err) {
        console.error('Failed to parse SSE event:', err);
      }
    };
    
    eventSource.onerror = (err) => {
      console.error('SSE error:', err);
      setError('Connection error. Please try again.');
      eventSource.close();
      setRetryingGameId(null);
    };
  };

  const retryAllMissing = async () => {
    if (!window.confirm(`Retry fetching all ${totalMissing} missing games?`)) {
      return;
    }
    
    setRetrying(true);
    setError(null);
    setSuccessMessage(null);
    setRetryProgress(null);
    setRetryResults([]);
    
    // Create EventSource for SSE
    const url = `${API_BASE_URL}/api/refresh/retry-missing-stream`;
    const eventSource = new EventSource(url, { withCredentials: true });
    eventSourceRef.current = eventSource;
    
    eventSource.onmessage = (event) => {
      try {
        const data: RetryProgressEvent = JSON.parse(event.data);
        
        switch (data.type) {
          case 'status':
            setRetryProgress(prev => ({
              current: prev?.current ?? 0,
              total: prev?.total ?? 0,
              message: data.message || '',
            }));
            break;
            
          case 'progress':
            setRetryProgress({
              current: data.current || 0,
              total: data.total || 0,
              message: data.message || `Processing ${data.matchup}...`,
            });
            break;
            
          case 'game_complete':
            if (data.game_id && data.status) {
              setRetryResults(prev => [...prev, {
                game_id: data.game_id!,
                status: data.status!,
                message: data.message || '',
              }]);
            }
            break;
            
          case 'done':
            setRetrying(false);
            setRetryProgress(null);
            if (data.data) {
              setSuccessMessage(
                `Retry complete: ${data.data.games_successful} successful, ${data.data.games_still_missing} still missing`
              );
            }
            eventSource.close();
            eventSourceRef.current = null;
            // Refresh the list
            fetchMissingGames();
            if (onRefresh) {
              onRefresh();
            }
            break;
            
          case 'error':
            setError(data.message || 'Unknown error occurred');
            setRetrying(false);
            setRetryProgress(null);
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
      setRetrying(false);
      setRetryProgress(null);
      eventSource.close();
      eventSourceRef.current = null;
    };
  };

  const formatDate = (dateStr: string) => {
    try {
      const date = new Date(dateStr + 'T00:00:00');
      return date.toLocaleDateString('en-US', { 
        month: 'short', 
        day: 'numeric', 
        year: 'numeric' 
      });
    } catch {
      return dateStr;
    }
  };

  // Cleanup EventSource on unmount
  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, []);

  // Fetch on mount
  useEffect(() => {
    fetchMissingGames();
  }, []);

  if (loading && totalMissing === 0) {
    return (
      <div className="text-center py-8">
        <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
        <p className="mt-2 text-sm text-gray-600">Loading missing games...</p>
      </div>
    );
  }

  if (totalMissing === 0) {
    return (
      <div className="text-center py-8">
        <svg className="mx-auto h-12 w-12 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <p className="mt-2 text-sm text-gray-600">No missing games - all scheduled games are cached</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header with Actions */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h3 className="text-lg font-semibold text-gray-900">Missing Games</h3>
          <p className="text-xs text-gray-500 mt-1">
            Games found in schedule but not in cache
          </p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <button
            onClick={fetchMissingGames}
            disabled={loading}
            className="px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100 rounded-lg transition-colors disabled:opacity-50"
            title="Refresh the list"
          >
            <svg className="w-4 h-4 inline mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            Refresh
          </button>
          <button
            onClick={retryAllMissing}
            disabled={retrying || totalMissing === 0}
            className="px-3 py-1.5 text-sm bg-blue-600 text-white hover:bg-blue-700 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {retrying ? 'Retrying...' : `Retry All (${totalMissing})`}
          </button>
        </div>
      </div>

      {/* Retry Progress */}
      {retrying && retryProgress && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
          <div className="flex items-center gap-3">
            <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-blue-600"></div>
            <div className="flex-1">
              <div className="flex justify-between items-center mb-1">
                <span className="text-sm font-medium text-blue-800">
                  {retryProgress.message}
                </span>
                <span className="text-sm text-blue-600">
                  {retryProgress.current} / {retryProgress.total}
                </span>
              </div>
              <div className="w-full bg-blue-200 rounded-full h-2">
                <div 
                  className="bg-blue-600 h-2 rounded-full transition-all duration-300"
                  style={{ width: `${retryProgress.total > 0 ? (retryProgress.current / retryProgress.total) * 100 : 0}%` }}
                />
              </div>
            </div>
          </div>
          
          {/* Recent results */}
          {retryResults.length > 0 && (
            <div className="mt-3 max-h-32 overflow-y-auto">
              {retryResults.slice(-5).map((result, idx) => (
                <div 
                  key={`${result.game_id}-${idx}`}
                  className={`text-xs py-1 ${
                    result.status === 'success' ? 'text-green-700' : 'text-red-700'
                  }`}
                >
                  {result.status === 'success' ? '✓' : '✗'} {result.message}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Messages */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-3">
          <p className="text-sm text-red-800">{error}</p>
        </div>
      )}
      
      {successMessage && (
        <div className="bg-green-50 border border-green-200 rounded-lg p-3">
          <p className="text-sm text-green-800">{successMessage}</p>
        </div>
      )}

      {/* Missing Games List */}
      <div className="space-y-4">
        {Object.entries(missingByDate)
          .sort(([dateA], [dateB]) => dateB.localeCompare(dateA))
          .map(([date, info]) => (
            <div key={date} className="border border-gray-200 rounded-lg overflow-hidden">
              {/* Date Header with Summary */}
              <div className="bg-gray-50 px-4 py-3 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <span className="font-medium text-gray-900">{formatDate(date)}</span>
                  <span className="text-sm text-gray-500">
                    {info.cached}/{info.expected} games cached
                  </span>
                  <span className="px-2 py-0.5 text-xs font-medium bg-blue-100 text-blue-800 rounded-full">
                    {info.missing_count} missing
                  </span>
                </div>
              </div>
              
              {/* Missing Games List */}
              <div className="divide-y divide-gray-100">
                {info.missing.map((game) => (
                  <div 
                    key={game.game_id}
                    className="px-4 py-3 flex items-center justify-between hover:bg-gray-50"
                  >
                    <div className="flex items-center gap-4">
                      <span className="text-sm font-medium text-gray-900">
                        {game.away_team_tricode} @ {game.home_team_tricode}
                      </span>
                      <span className="text-xs text-gray-500 font-mono">
                        {game.game_id}
                      </span>
                    </div>
                    <button
                      onClick={() => retryGame(game.game_id)}
                      disabled={retryingGameId === game.game_id || retrying}
                      className="text-sm text-blue-600 hover:text-blue-800 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {retryingGameId === game.game_id ? 'Retrying...' : 'Retry'}
                    </button>
                  </div>
                ))}
              </div>
            </div>
          ))}
      </div>
    </div>
  );
}

