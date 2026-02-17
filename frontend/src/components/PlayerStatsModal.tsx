/**
 * Modal component for displaying player stats
 */

import { useState, useEffect } from 'react';
import { api } from '../services/api';
import type { PlayerStatsResponse, GameLog } from '../types/api';
import { StatCell } from './StatCell';
import { useLeague } from '../context/LeagueContext';

interface PlayerStatsModalProps {
  playerId: number | null;
  playerName: string;
  isOpen: boolean;
  onClose: () => void;
}

export function PlayerStatsModal({ playerId, playerName, isOpen, onClose }: PlayerStatsModalProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [playerStats, setPlayerStats] = useState<PlayerStatsResponse | null>(null);
  const { defaultLeagueKey } = useLeague();

  // Track if player is not in NBA database
  const isPlayerNotInNba = playerId === null;

  useEffect(() => {
    if (isOpen && playerId) {
      fetchPlayerStats();
    }
    // Reset state when modal opens for a player not in NBA
    if (isOpen && !playerId) {
      setPlayerStats(null);
      setError(null);
      setLoading(false);
    }
  }, [isOpen, playerId]);

  const fetchPlayerStats = async () => {
    if (!playerId) return;
    
    setLoading(true);
    setError(null);
    try {
      const data = await api.getPlayerStats(playerId, 'Regular Season', defaultLeagueKey || undefined);
      setPlayerStats(data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to fetch player stats');
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div 
        className="bg-white rounded-xl shadow-2xl max-w-6xl w-full max-h-[90vh] overflow-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 flex justify-between items-center">
          <div className="flex items-center gap-3">
            <h2 className="text-2xl font-bold text-neutral-900">{playerStats?.player_name || playerName}</h2>
            {playerStats?.rank && (
              <span 
                className={`inline-flex items-center px-2.5 py-1 rounded-full text-sm font-bold ${
                  playerStats.rank <= 25 
                    ? 'bg-green-100 text-green-800' 
                    : playerStats.rank <= 75 
                      ? 'bg-blue-100 text-blue-800' 
                      : playerStats.rank <= 150 
                        ? 'bg-gray-100 text-gray-800' 
                        : 'bg-gray-50 text-gray-500'
                }`}
                title="Yahoo Fantasy Rank (Actual Rank)"
              >
                #{playerStats.rank}
              </span>
            )}
            {playerStats?.team_tricode && (
              <span className="text-lg font-semibold text-gray-500">
                {playerStats.team_tricode}
              </span>
            )}
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 transition-colors text-2xl font-bold"
          >
            ×
          </button>
        </div>

        <div className="p-6">
          {loading && (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-neutral-900"></div>
            </div>
          )}

          {error && (
            <div className="bg-red-50 border border-red-200 rounded-xl p-5">
              <p className="text-red-600">{error}</p>
            </div>
          )}

          {isPlayerNotInNba && !loading && (
            <div className="bg-amber-50 border border-amber-200 rounded-xl p-8 text-center">
              <div className="text-amber-600 text-5xl mb-4">?</div>
              <h3 className="text-lg font-semibold text-amber-800 mb-2">Player Not Found in NBA Database</h3>
              <p className="text-amber-700">
                {playerName} is not available in the NBA stats database. This player may be in the G-League, 
                overseas, or recently added to a roster.
              </p>
            </div>
          )}

          {playerStats && !loading && !error && !isPlayerNotInNba && (
            <div className="space-y-6">
              {/* Recent and Upcoming Games */}
              {(playerStats.recent_games && playerStats.recent_games.length > 0) || (playerStats.upcoming_games && playerStats.upcoming_games.length > 0) ? (
                <div className="card overflow-hidden">
                  <div className="px-6 py-4 border-b border-gray-200 bg-neutral-50">
                    <h3 className="text-lg font-bold text-neutral-900">Recent and Upcoming Games</h3>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-gray-200">
                      <thead className="bg-neutral-50">
                        <tr>
                          <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                            Date
                          </th>
                          <th className="px-4 py-3 text-center text-xs font-semibold text-gray-600 uppercase tracking-wider">
                            Week
                          </th>
                          <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                            Matchup
                          </th>
                          <th className="px-4 py-3 text-center text-xs font-semibold text-gray-600 uppercase tracking-wider">
                            W/L
                          </th>
                          <th className="px-4 py-3 text-center text-xs font-semibold text-gray-600 uppercase tracking-wider">
                            Score
                          </th>
                          <th className="px-4 py-3 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">
                            MIN
                          </th>
                          <th className="px-4 py-3 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">
                            FG%
                          </th>
                          <th className="px-4 py-3 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">
                            FT%
                          </th>
                          <th className="px-4 py-3 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">
                            3PM
                          </th>
                          <th className="px-4 py-3 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">
                            PTS
                          </th>
                          <th className="px-4 py-3 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">
                            REB
                          </th>
                          <th className="px-4 py-3 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">
                            AST
                          </th>
                          <th className="px-4 py-3 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">
                            STL
                          </th>
                          <th className="px-4 py-3 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">
                            BLK
                          </th>
                          <th className="px-4 py-3 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">
                            TO
                          </th>
                          <th className="px-4 py-3 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">
                            USG%
                          </th>
                        </tr>
                      </thead>
                      <tbody className="bg-white divide-y divide-gray-100">
                        {playerStats.recent_games.map((game: GameLog, idx: number) => (
                          <tr key={`recent-${idx}`} className="hover:bg-neutral-50 transition-colors">
                            <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-600">
                              {game.date}
                            </td>
                            <td className="px-4 py-3 text-center text-sm text-gray-500">
                              {game.fantasy_week || '-'}
                            </td>
                            <td className="px-4 py-3 whitespace-nowrap text-sm font-medium text-neutral-900">
                              {game.matchup}
                            </td>
                            <td className={`px-4 py-3 text-center text-sm font-semibold ${
                              game.wl === 'W' ? 'text-green-600' : game.wl === 'L' ? 'text-red-500' : 'text-gray-400'
                            }`}>
                              {game.wl || '-'}
                            </td>
                            <td className="px-4 py-3 text-center text-sm text-gray-600">
                              {game.score || '-'}
                            </td>
                            <td className="px-4 py-3 text-right text-sm text-gray-600">
                              {game.minutes.toFixed(1)}
                            </td>
                            <StatCell
                              statName="FG%"
                              value={game.fg_pct}
                              attempts={{ made: game.fgm, attempts: game.fga }}
                              aggMode="last"
                            />
                            <StatCell
                              statName="FT%"
                              value={game.ft_pct}
                              attempts={{ made: game.ftm, attempts: game.fta }}
                              aggMode="last"
                            />
                            <StatCell statName="3PM" value={game.threes} aggMode="last" />
                            <StatCell statName="PTS" value={game.points} aggMode="last" />
                            <StatCell statName="REB" value={game.rebounds} aggMode="last" />
                            <StatCell statName="AST" value={game.assists} aggMode="last" />
                            <StatCell statName="STL" value={game.steals} aggMode="last" />
                            <StatCell statName="BLK" value={game.blocks} aggMode="last" />
                            <StatCell statName="TO" value={game.turnovers} aggMode="last" />
                            <StatCell statName="USG%" value={game.usage_pct} aggMode="last" />
                          </tr>
                        ))}
                        {playerStats.upcoming_games && playerStats.upcoming_games.map((game: GameLog, idx: number) => (
                          <tr key={`upcoming-${idx}`} className="hover:bg-neutral-50 transition-colors bg-blue-50">
                            <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-500 italic">
                              {game.date}
                            </td>
                            <td className="px-4 py-3 text-center text-sm text-gray-500 italic">
                              {game.fantasy_week || '-'}
                            </td>
                            <td className="px-4 py-3 whitespace-nowrap text-sm font-medium text-gray-500 italic">
                              {game.matchup}
                            </td>
                            <td className="px-4 py-3 text-center text-sm text-gray-400">-</td>
                            <td className="px-4 py-3 text-center text-sm text-gray-400">-</td>
                            <td className="px-4 py-3 text-right text-sm text-gray-400">
                              -
                            </td>
                            <td className="px-4 py-3 text-right text-sm text-gray-400">-</td>
                            <td className="px-4 py-3 text-right text-sm text-gray-400">-</td>
                            <td className="px-4 py-3 text-right text-sm text-gray-400">-</td>
                            <td className="px-4 py-3 text-right text-sm text-gray-400">-</td>
                            <td className="px-4 py-3 text-right text-sm text-gray-400">-</td>
                            <td className="px-4 py-3 text-right text-sm text-gray-400">-</td>
                            <td className="px-4 py-3 text-right text-sm text-gray-400">-</td>
                            <td className="px-4 py-3 text-right text-sm text-gray-400">-</td>
                            <td className="px-4 py-3 text-right text-sm text-gray-400">-</td>
                            <td className="px-4 py-3 text-right text-sm text-gray-400">-</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ) : null}

              {/* Average Stats */}
              <div className="card overflow-hidden">
                <div className="px-6 py-4 border-b border-gray-200 bg-neutral-50">
                  <h3 className="text-lg font-bold text-neutral-900">Average Stats</h3>
                </div>
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-neutral-50">
                      <tr>
                        <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                          Period
                        </th>
                        <th className="px-4 py-3 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">
                          FG%
                        </th>
                        <th className="px-4 py-3 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">
                          FT%
                        </th>
                        <th className="px-4 py-3 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">
                          3PM
                        </th>
                        <th className="px-4 py-3 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">
                          PTS
                        </th>
                        <th className="px-4 py-3 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">
                          REB
                        </th>
                        <th className="px-4 py-3 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">
                          AST
                        </th>
                        <th className="px-4 py-3 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">
                          STL
                        </th>
                        <th className="px-4 py-3 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">
                          BLK
                        </th>
                        <th className="px-4 py-3 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">
                          TO
                        </th>
                        <th className="px-4 py-3 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">
                          USG%
                        </th>
                        <th className="px-4 py-3 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">
                          Starter
                        </th>
                        <th className="px-4 py-3 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">
                          MIN
                        </th>
                      </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-100">
                      {[
                        { name: 'Last 3', stats: playerStats.last3 },
                        { name: 'Last 7', stats: playerStats.last7 },
                        { name: 'Season', stats: playerStats.season },
                      ].map((period) => {
                        const aggMode = 'avg';
                        
                        return (
                          <tr key={period.name} className="hover:bg-neutral-50 transition-colors">
                            <td className="px-4 py-3 whitespace-nowrap text-sm font-medium text-cyan-600">
                              {period.name}
                            </td>
                            {period.stats ? (
                              <>
                                <StatCell
                                  statName="FG%"
                                  value={period.stats.fg_pct}
                                  attempts={{ made: period.stats.fgm, attempts: period.stats.fga }}
                                  aggMode={aggMode}
                                />
                                <StatCell
                                  statName="FT%"
                                  value={period.stats.ft_pct}
                                  attempts={{ made: period.stats.ftm, attempts: period.stats.fta }}
                                  aggMode={aggMode}
                                />
                                <StatCell statName="3PM" value={period.stats.threes} aggMode={aggMode} />
                                <StatCell statName="PTS" value={period.stats.points} aggMode={aggMode} />
                                <StatCell statName="REB" value={period.stats.rebounds} aggMode={aggMode} />
                                <StatCell statName="AST" value={period.stats.assists} aggMode={aggMode} />
                                <StatCell statName="STL" value={period.stats.steals} aggMode={aggMode} />
                                <StatCell statName="BLK" value={period.stats.blocks} aggMode={aggMode} />
                                <StatCell statName="TO" value={period.stats.turnovers} aggMode={aggMode} />
                                <StatCell statName="USG%" value={period.stats.usage_pct} aggMode={aggMode} />
                                <td className="px-4 py-3 text-right text-sm text-neutral-900">
                                  {period.stats.games_started}
                                </td>
                                <StatCell statName="MIN" value={period.stats.minutes} aggMode={aggMode} />
                              </>
                            ) : (
                              <td colSpan={12} className="px-4 py-3 text-center text-sm text-gray-500">
                                N/A
                              </td>
                            )}
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

