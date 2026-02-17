/**
 * Player search page
 */

import { useState, useEffect } from 'react';
import { Layout } from '../components/Layout';
import { PlayerTable } from '../components/PlayerTable';
import { PlayerStatsModal } from '../components/PlayerStatsModal';
import { Dropdown } from '../components/Dropdown';
import { StatCell } from '../components/StatCell';
import { api } from '../services/api';
import { useLeague } from '../context/LeagueContext';
import type { PlayerStatsResponse, PlayerSuggestion, RankedPlayer } from '../types/api';
import { getTrendColor, getColorClass } from '../utils/statColors';

type RankFilter = 'top50' | 'top100' | 'top150' | 'top200' | 'all';
type RankingMode = 'yahoo' | '9cat';

export function PlayerSearch() {
  const { defaultLeagueKey } = useLeague();
  const [searchName, setSearchName] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<PlayerSuggestion[]>([]);
  const [playerStats, setPlayerStats] = useState<PlayerStatsResponse | null>(null);
  
  // Ranked players state
  const [rankFilter, setRankFilter] = useState<RankFilter>('top150');
  const [lookback, setLookback] = useState('season');
  const [aggMode, setAggMode] = useState('avg');
  const [rankingMode, setRankingMode] = useState<RankingMode>('yahoo');
  const [rankedPlayers, setRankedPlayers] = useState<RankedPlayer[]>([]);
  const [rankedLoading, setRankedLoading] = useState(false);
  const [rankedError, setRankedError] = useState<string | null>(null);
  const [selectedPlayer, setSelectedPlayer] = useState<{ id: number; name: string } | null>(null);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchName.trim()) return;

    setLoading(true);
    setError(null);
    setSuggestions([]);
    setPlayerStats(null);

    try {
      const result = await api.searchPlayers(searchName.trim());
      
      if (result.exact_match && result.suggestions.length === 1) {
        // Fetch full stats for exact match
        const stats = await api.getPlayerStats(result.suggestions[0].player_id);
        setPlayerStats(stats);
      } else {
        // Show suggestions
        setSuggestions(result.suggestions);
      }
    } catch (err: any) {
      if (err.response?.status === 401) {
        setError('Authentication required. Please log in again.');
      } else if (err.response?.status === 404) {
        setError('Player not found. Please try a different name.');
      } else if (err.response?.status === 500) {
        setError(err.response?.data?.detail || 'Server error. Please try again later.');
      } else if (!navigator.onLine) {
        setError('Network error. Please check your connection.');
      } else {
        setError(err.response?.data?.detail || 'Failed to search for player. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleSelectPlayer = async (playerId: number) => {
    setLoading(true);
    setError(null);
    setSuggestions([]);

    try {
      const stats = await api.getPlayerStats(playerId);
      setPlayerStats(stats);
    } catch (err: any) {
      if (err.response?.status === 401) {
        setError('Authentication required. Please log in again.');
      } else if (err.response?.status === 404) {
        setError('Player stats not found.');
      } else if (err.response?.status === 500) {
        setError(err.response?.data?.detail || 'Server error. Please try again later.');
      } else if (!navigator.onLine) {
        setError('Network error. Please check your connection.');
      } else {
        setError(err.response?.data?.detail || 'Failed to fetch player stats. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  };

  // Fetch ranked players when league key or filters change
  useEffect(() => {
    const fetchRankedPlayers = async () => {
      if (!defaultLeagueKey) return;

      setRankedLoading(true);
      setRankedError(null);

      try {
        const maxRank = rankFilter === 'all' ? 9999 : parseInt(rankFilter.replace('top', ''));
        const result = await api.getRankedPlayers(defaultLeagueKey, {
          maxRank,
          statsMode: lookback,
          aggMode,
          rankingMode,
        });
        setRankedPlayers(result.players);
      } catch (err: any) {
        if (err.response?.status === 404) {
          setRankedError('No rankings found. Rankings need to be refreshed.');
        } else {
          setRankedError(err.response?.data?.detail || 'Failed to fetch ranked players.');
        }
      } finally {
        setRankedLoading(false);
      }
    };

    fetchRankedPlayers();
  }, [defaultLeagueKey, rankFilter, lookback, aggMode, rankingMode]);

  const trendColor = playerStats ? getTrendColor(playerStats.trend) : 'dim';
  const trendColorClass = getColorClass(trendColor);
  const trendDirection = playerStats && playerStats.trend > 0 ? '↑ trending up' : 
                         playerStats && playerStats.trend < 0 ? '↓ trending down' : 'stable';

  return (
    <Layout>
      <div className="px-4 py-4 md:py-6">
        <h1 className="text-2xl md:text-3xl font-bold text-neutral-900 mb-4 md:mb-6">Players</h1>

        <form onSubmit={handleSearch} className="mb-4">
          <div className="flex gap-2 max-w-md">
            <input
              type="text"
              value={searchName}
              onChange={(e) => setSearchName(e.target.value)}
              placeholder="Enter player name..."
              className="flex-1 px-3 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-neutral-900 focus:border-transparent transition-all text-sm"
            />
            <button
              type="submit"
              disabled={loading}
              className="px-4 py-2 bg-neutral-900 text-white rounded-lg hover:bg-neutral-850 disabled:opacity-50 disabled:cursor-not-allowed transition-colors font-medium text-sm"
            >
              {loading ? 'Searching...' : 'Search'}
            </button>
          </div>
        </form>

        {error && (
          <div className="bg-red-50 border border-red-200 rounded-xl p-4 md:p-5 mb-4 md:mb-6">
            <p className="text-red-600 text-sm md:text-base">{error}</p>
          </div>
        )}

        {suggestions.length > 0 && (
          <div className="card p-4 md:p-6 mb-4 md:mb-6">
            <h2 className="text-lg md:text-xl font-semibold text-neutral-900 mb-3 md:mb-4">
              Select a player:
            </h2>
            <div className="space-y-2">
              {suggestions.map((suggestion, idx) => (
                <button
                  key={suggestion.player_id}
                  onClick={() => handleSelectPlayer(suggestion.player_id)}
                  className="w-full text-left px-4 md:px-5 py-3 md:py-3.5 bg-neutral-50 hover:bg-neutral-100 rounded-xl transition-all hover:shadow-card border border-transparent hover:border-gray-200"
                >
                  <span className="text-gray-400 mr-3 md:mr-4 text-xs md:text-sm">{idx + 1}.</span>
                  <span className="text-neutral-900 font-medium text-sm md:text-base">{suggestion.full_name}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {playerStats && (
          <div className="space-y-4 md:space-y-6">
            <PlayerTable
              playerName={playerStats.player_name}
              playerId={playerStats.player_id}
              periods={[
                {
                  name: 'Last Game',
                  stats: playerStats.last_game,
                },
                {
                  name: 'Last 3',
                  stats: playerStats.last3,
                },
                {
                  name: 'Last 7',
                  stats: playerStats.last7,
                },
                {
                  name: 'Season',
                  stats: playerStats.season,
                },
              ]}
            />

            <div className="card p-4 md:p-5">
              <p className="text-xs md:text-sm text-gray-700">
                <span className="font-medium">Minute Trend:</span>{' '}
                <span className={trendColorClass + ' font-semibold'}>
                  {playerStats.trend > 0 ? '+' : ''}{playerStats.trend.toFixed(1)}
                </span>
                {' '}
                <span className="text-gray-500">
                  ({trendDirection} from 3-game average)
                </span>
              </p>
            </div>
          </div>
        )}

        {/* Ranked Players Section */}
        {defaultLeagueKey && (
          <div className="mt-8">
            <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 mb-4">
              <h2 className="text-xl md:text-2xl font-bold text-neutral-900">Player Rankings</h2>
              <div className="flex flex-wrap items-center gap-3">
                <div className="flex items-center gap-2">
                  <label className="text-sm font-medium text-gray-700">Ranking:</label>
                  <Dropdown
                    value={rankingMode}
                    onChange={(value) => setRankingMode(value as RankingMode)}
                    options={[
                      { value: 'yahoo', label: 'Yahoo' },
                      { value: '9cat', label: '9-Cat' },
                    ]}
                    className="w-24"
                  />
                </div>
                <div className="flex items-center gap-2">
                  <label className="text-sm font-medium text-gray-700">Rank:</label>
                  <Dropdown
                    value={rankFilter}
                    onChange={(value) => setRankFilter(value as RankFilter)}
                    options={[
                      { value: 'top50', label: 'Top 50' },
                      { value: 'top100', label: 'Top 100' },
                      { value: 'top150', label: 'Top 150' },
                      { value: 'top200', label: 'Top 200' },
                      { value: 'all', label: 'All' },
                    ]}
                    className="w-28"
                  />
                </div>
                <div className="flex items-center gap-2">
                  <label className="text-sm font-medium text-gray-700">Period:</label>
                  <Dropdown
                    value={lookback}
                    onChange={(value) => setLookback(String(value))}
                    options={[
                      { value: 'last', label: 'Last Game' },
                      { value: 'last3', label: 'Last 3' },
                      { value: 'last7', label: 'Last 7' },
                      { value: 'last7d', label: '7 Days' },
                      { value: 'last14d', label: '14 Days' },
                      { value: 'last30d', label: '30 Days' },
                      { value: 'season', label: 'Season' },
                    ]}
                    className="w-28"
                  />
                </div>
                <div className="flex items-center gap-2">
                  <label className="text-sm font-medium text-gray-700">Show:</label>
                  <Dropdown
                    value={aggMode}
                    onChange={(value) => setAggMode(String(value))}
                    options={[
                      { value: 'avg', label: 'Average' },
                      { value: 'sum', label: 'Sum' },
                    ]}
                    className="w-24"
                  />
                </div>
              </div>
            </div>

            {rankedError && (
              <div className="bg-red-50 border border-red-200 rounded-xl p-4 md:p-5 mb-4">
                <p className="text-red-600 text-sm md:text-base">{rankedError}</p>
              </div>
            )}

            {rankedLoading && (
              <div className="card overflow-hidden">
                <div className="flex flex-col items-center justify-center py-20">
                  <div className="animate-spin rounded-full h-16 w-16 border-b-2 border-neutral-900 mb-4"></div>
                  <p className="text-neutral-900 font-semibold text-lg">Loading ranked players...</p>
                  <p className="text-gray-600 text-sm mt-2">This may take a moment</p>
                </div>
              </div>
            )}

            {!rankedLoading && rankedPlayers.length > 0 && (
              <div className="card overflow-hidden">
                <div className="overflow-x-auto touch-scroll">
                  <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-neutral-50">
                      <tr>
                        <th className="sticky left-0 z-20 px-3 py-2 text-center text-xs font-semibold text-gray-600 uppercase tracking-wider bg-neutral-50">
                          Rank
                        </th>
                        <th className="sticky left-12 z-20 px-3 py-2 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider bg-neutral-50 shadow-[2px_0_4px_-2px_rgba(0,0,0,0.1)]">
                          Player
                        </th>
                        <th className="px-2 py-2 text-center text-xs font-semibold text-gray-600 uppercase tracking-wider">
                          Team
                        </th>
                        {rankingMode === '9cat' && (
                          <th className="px-2 py-2 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">
                            Z-Score
                          </th>
                        )}
                        <th className="px-2 py-2 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">
                          GP
                        </th>
                        <th className="px-2 py-2 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">
                          MIN
                        </th>
                        <th className="px-2 py-2 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">
                          FGM
                        </th>
                        <th className="px-2 py-2 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">
                          FGA
                        </th>
                        <th className="px-2 py-2 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">
                          FG%
                        </th>
                        <th className="px-2 py-2 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">
                          FTM
                        </th>
                        <th className="px-2 py-2 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">
                          FTA
                        </th>
                        <th className="px-2 py-2 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">
                          FT%
                        </th>
                        <th className="px-2 py-2 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">
                          3PM
                        </th>
                        <th className="px-2 py-2 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">
                          PTS
                        </th>
                        <th className="px-2 py-2 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">
                          REB
                        </th>
                        <th className="px-2 py-2 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">
                          AST
                        </th>
                        <th className="px-2 py-2 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">
                          STL
                        </th>
                        <th className="px-2 py-2 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">
                          BLK
                        </th>
                        <th className="px-2 py-2 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">
                          TO
                        </th>
                      </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-100">
                      {rankedPlayers.map((player) => (
                        <tr key={player.player_id} className="hover:bg-neutral-50 transition-colors group">
                          <td className={`sticky left-0 z-10 px-3 py-1.5 text-center text-xs font-medium bg-white group-hover:bg-neutral-50 transition-colors ${
                            player.rank <= 25 ? 'text-green-600' :
                            player.rank <= 75 ? 'text-blue-600' :
                            player.rank <= 150 ? 'text-gray-600' : 'text-gray-400'
                          }`}>
                            {player.rank}
                          </td>
                          <td className="sticky left-12 z-10 px-3 py-1.5 whitespace-nowrap text-xs font-medium bg-white group-hover:bg-neutral-50 shadow-[2px_0_4px_-2px_rgba(0,0,0,0.1)] transition-colors">
                            <button
                              onClick={() => setSelectedPlayer({ id: player.player_id, name: player.player_name })}
                              className="text-cyan-600 hover:text-cyan-700 hover:underline transition-colors cursor-pointer"
                            >
                              {player.player_name}
                            </button>
                          </td>
                          <td className="px-2 py-1.5 text-center text-xs text-gray-600">
                            {player.team_tricode || '-'}
                          </td>
                          {rankingMode === '9cat' && (
                            <td className={`px-2 py-1.5 text-right text-xs font-medium ${
                              player.z_score !== null && player.z_score > 0 ? 'text-green-600' :
                              player.z_score !== null && player.z_score < 0 ? 'text-red-600' : 'text-gray-600'
                            }`}>
                              {player.z_score !== null ? (player.z_score > 0 ? '+' : '') + player.z_score.toFixed(2) : '-'}
                            </td>
                          )}
                          {player.stats ? (
                            <>
                              <td className="px-2 py-1.5 text-right text-xs text-gray-600">
                                {player.stats.games_count}
                              </td>
                              <td className="px-2 py-1.5 text-right text-xs text-gray-600">
                                {player.stats.minutes.toFixed(1)}
                              </td>
                              <StatCell statName="FGM" value={player.stats.fgm} aggMode={lookback === 'last' ? 'last' : (aggMode as 'avg' | 'sum')} />
                              <StatCell statName="FGA" value={player.stats.fga} aggMode={lookback === 'last' ? 'last' : (aggMode as 'avg' | 'sum')} />
                              <StatCell statName="FG%" value={player.stats.fg_pct} aggMode={lookback === 'last' ? 'last' : (aggMode as 'avg' | 'sum')} />
                              <StatCell statName="FTM" value={player.stats.ftm} aggMode={lookback === 'last' ? 'last' : (aggMode as 'avg' | 'sum')} />
                              <StatCell statName="FTA" value={player.stats.fta} aggMode={lookback === 'last' ? 'last' : (aggMode as 'avg' | 'sum')} />
                              <StatCell statName="FT%" value={player.stats.ft_pct} aggMode={lookback === 'last' ? 'last' : (aggMode as 'avg' | 'sum')} />
                              <StatCell statName="3PM" value={player.stats.threes} aggMode={lookback === 'last' ? 'last' : (aggMode as 'avg' | 'sum')} />
                              <StatCell statName="PTS" value={player.stats.points} aggMode={lookback === 'last' ? 'last' : (aggMode as 'avg' | 'sum')} />
                              <StatCell statName="REB" value={player.stats.rebounds} aggMode={lookback === 'last' ? 'last' : (aggMode as 'avg' | 'sum')} />
                              <StatCell statName="AST" value={player.stats.assists} aggMode={lookback === 'last' ? 'last' : (aggMode as 'avg' | 'sum')} />
                              <StatCell statName="STL" value={player.stats.steals} aggMode={lookback === 'last' ? 'last' : (aggMode as 'avg' | 'sum')} />
                              <StatCell statName="BLK" value={player.stats.blocks} aggMode={lookback === 'last' ? 'last' : (aggMode as 'avg' | 'sum')} />
                              <StatCell statName="TO" value={player.stats.turnovers} aggMode={lookback === 'last' ? 'last' : (aggMode as 'avg' | 'sum')} />
                            </>
                          ) : (
                            <td colSpan={rankingMode === '9cat' ? 16 : 15} className="px-2 py-1.5 text-center text-xs text-gray-500">
                              No stats available
                            </td>
                          )}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {!rankedLoading && rankedPlayers.length === 0 && !rankedError && (
              <div className="card p-8 text-center">
                <p className="text-gray-600">No ranked players found.</p>
              </div>
            )}
          </div>
        )}

        {!defaultLeagueKey && (
          <div className="mt-8 bg-blue-50 border border-blue-200 rounded-xl p-5">
            <p className="text-blue-800 font-semibold">No league selected</p>
            <p className="text-blue-700 text-sm mt-1.5">
              Please <a href="/" className="underline font-medium">select a league</a> from the home page to see player rankings.
            </p>
          </div>
        )}
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

