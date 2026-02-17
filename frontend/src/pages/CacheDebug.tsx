/**
 * Cache Debug Page
 * Displays comprehensive information about cached data
 */

import { useEffect, useState } from 'react';
import { Layout } from '../components/Layout';
import { api } from '../services/api';
import type { CacheDebugResponse, GameFileInfo, ScheduleFileInfo, PlayerSeasonStats } from '../types/api';

export function CacheDebug() {
  const [data, setData] = useState<CacheDebugResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({});
  
  // Modal states
  const [selectedGame, setSelectedGame] = useState<GameFileInfo | null>(null);
  const [selectedPlayer, setSelectedPlayer] = useState<PlayerSeasonStats | null>(null);
  
  // Search states
  const [playerSearchTerm, setPlayerSearchTerm] = useState('');

  useEffect(() => {
    loadCacheData();
  }, []);

  const loadCacheData = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await api.getCacheDebugData();
      setData(response);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to load cache data');
    } finally {
      setLoading(false);
    }
  };

  const toggleSection = (section: string) => {
    setExpandedSections(prev => ({
      ...prev,
      [section]: !prev[section]
    }));
  };

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return 'N/A';
    return new Date(dateStr).toLocaleDateString();
  };

  const closeGameModal = () => setSelectedGame(null);
  const closePlayerModal = () => setSelectedPlayer(null);

  if (loading) {
    return (
      <Layout>
        <div className="px-4 py-6 max-w-7xl mx-auto">
          <div className="animate-pulse space-y-4">
            <div className="h-8 bg-gray-200 rounded w-1/3"></div>
            <div className="h-32 bg-gray-200 rounded"></div>
            <div className="h-64 bg-gray-200 rounded"></div>
          </div>
        </div>
      </Layout>
    );
  }

  if (error) {
    return (
      <Layout>
        <div className="px-4 py-6 max-w-7xl mx-auto">
          <div className="bg-red-50 border border-red-200 rounded-xl p-6">
            <h2 className="text-xl font-semibold text-red-800 mb-2">Error Loading Cache Data</h2>
            <p className="text-red-700">{error}</p>
            <button
              onClick={loadCacheData}
              className="mt-4 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors"
            >
              Retry
            </button>
          </div>
        </div>
      </Layout>
    );
  }

  if (!data) {
    return (
      <Layout>
        <div className="px-4 py-6 max-w-7xl mx-auto">
          <p className="text-gray-600">No cache data available</p>
        </div>
      </Layout>
    );
  }

  const { boxscore_cache, schedule_cache, metadata } = data;

  return (
    <Layout>
      <div className="px-4 py-6 max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-6">
          <h1 className="text-3xl font-bold text-neutral-900 mb-2">Cache Debug</h1>
          <p className="text-gray-600">Detailed view of cached game schedules and box scores</p>
        </div>

        {/* Summary Statistics */}
        <div className="card p-6 mb-6">
          <h2 className="text-xl font-semibold text-neutral-900 mb-4">Summary Statistics</h2>
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Box Score Cache Summary */}
            <div className="bg-blue-50 rounded-lg p-4 border border-blue-200">
              <h3 className="font-semibold text-blue-900 mb-3 flex items-center gap-2">
                <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                  <path d="M9 2a1 1 0 000 2h2a1 1 0 100-2H9z" />
                  <path fillRule="evenodd" d="M4 5a2 2 0 012-2 3 3 0 003 3h2a3 3 0 003-3 2 2 0 012 2v11a2 2 0 01-2 2H6a2 2 0 01-2-2V5zm3 4a1 1 0 000 2h.01a1 1 0 100-2H7zm3 0a1 1 0 000 2h3a1 1 0 100-2h-3zm-3 4a1 1 0 100 2h.01a1 1 0 100-2H7zm3 0a1 1 0 100 2h3a1 1 0 100-2h-3z" clipRule="evenodd" />
                </svg>
                Box Score Cache
              </h3>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-blue-700">Total Games:</span>
                  <span className="font-semibold text-blue-900">{boxscore_cache.total_games}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-blue-700">Players Indexed:</span>
                  <span className="font-semibold text-blue-900">{boxscore_cache.total_players}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-blue-700">Date Range:</span>
                  <span className="font-semibold text-blue-900">
                    {formatDate(boxscore_cache.date_range.start)} - {formatDate(boxscore_cache.date_range.end)}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-blue-700">Seasons:</span>
                  <span className="font-semibold text-blue-900">
                    {Object.keys(boxscore_cache.games_by_season).length}
                  </span>
                </div>
              </div>
            </div>

            {/* Schedule Cache Summary */}
            <div className="bg-green-50 rounded-lg p-4 border border-green-200">
              <h3 className="font-semibold text-green-900 mb-3 flex items-center gap-2">
                <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M6 2a1 1 0 00-1 1v1H4a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V6a2 2 0 00-2-2h-1V3a1 1 0 10-2 0v1H7V3a1 1 0 00-1-1zm0 5a1 1 0 000 2h8a1 1 0 100-2H6z" clipRule="evenodd" />
                </svg>
                Schedule Cache
              </h3>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-green-700">Team Schedules:</span>
                  <span className="font-semibold text-green-900">{schedule_cache.total_schedules}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-green-700">Player-Team Index:</span>
                  <span className="font-semibold text-green-900">{schedule_cache.total_player_indexes}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-green-700">Seasons:</span>
                  <span className="font-semibold text-green-900">
                    {Object.keys(schedule_cache.schedules_by_season).length}
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Metadata */}
          <div className="mt-6 pt-6 border-t border-gray-200">
            <h3 className="font-semibold text-gray-900 mb-3">Metadata</h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
              <div>
                <span className="text-gray-600">Season:</span>
                <span className="ml-2 font-semibold text-gray-900">{metadata.season || 'N/A'}</span>
              </div>
              <div>
                <span className="text-gray-600">Games Cached:</span>
                <span className="ml-2 font-semibold text-gray-900">{metadata.games_cached}</span>
              </div>
              <div>
                <span className="text-gray-600">Last Updated:</span>
                <span className="ml-2 font-semibold text-gray-900">
                  {metadata.last_updated ? new Date(metadata.last_updated).toLocaleString() : 'N/A'}
                </span>
              </div>
            </div>
          </div>

          {/* Cache Directories */}
          <div className="mt-4 pt-4 border-t border-gray-200">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
              <div>
                <span className="text-gray-600">Box Score Directory:</span>
                <div className="mt-1 font-mono text-gray-800 bg-gray-100 p-2 rounded break-all">
                  {boxscore_cache.cache_dir}
                </div>
              </div>
              <div>
                <span className="text-gray-600">Schedule Directory:</span>
                <div className="mt-1 font-mono text-gray-800 bg-gray-100 p-2 rounded break-all">
                  {schedule_cache.cache_dir}
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Box Score Games by Season */}
        <div className="card p-6 mb-6">
          <button
            onClick={() => toggleSection('boxscore-games')}
            className="w-full flex items-center justify-between mb-4 hover:bg-gray-50 -m-2 p-2 rounded transition-colors"
          >
            <h2 className="text-xl font-semibold text-neutral-900">
              Box Score Games ({boxscore_cache.total_games} total)
            </h2>
            <svg 
              className={`w-5 h-5 transition-transform ${expandedSections['boxscore-games'] ? 'rotate-180' : ''}`}
              fill="none" 
              stroke="currentColor" 
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </button>

          {expandedSections['boxscore-games'] && (
            <div className="space-y-4">
              {Object.entries(boxscore_cache.games_by_season).map(([season, games]) => (
                <div key={season} className="border border-gray-200 rounded-lg p-4">
                  <h3 className="font-semibold text-gray-900 mb-3">
                    Season {season} ({games.length} games)
                  </h3>
                  <div className="max-h-96 overflow-y-auto">
                    <table className="min-w-full text-sm">
                      <thead className="bg-gray-50 sticky top-0">
                        <tr>
                          <th className="px-3 py-2 text-left text-xs font-medium text-gray-700 uppercase">Date</th>
                          <th className="px-3 py-2 text-left text-xs font-medium text-gray-700 uppercase">Matchup</th>
                          <th className="px-3 py-2 text-left text-xs font-medium text-gray-700 uppercase">Score</th>
                          <th className="px-3 py-2 text-left text-xs font-medium text-gray-700 uppercase">Game ID</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-200">
                        {games.map((game: GameFileInfo) => (
                          <tr 
                            key={game.filename} 
                            onClick={() => game.box_score && setSelectedGame(game)}
                            className={`hover:bg-blue-50 ${game.box_score ? 'cursor-pointer' : ''}`}
                          >
                            <td className="px-3 py-2 text-gray-900">{game.game_date}</td>
                            <td className="px-3 py-2 text-gray-900 font-medium">
                              {game.matchup || game.home_team && game.away_team ? 
                                `${game.away_team} @ ${game.home_team}` : 
                                'N/A'}
                            </td>
                            <td className="px-3 py-2 text-gray-700">
                              {game.away_score !== null && game.home_score !== null ?
                                `${game.away_score} - ${game.home_score}` :
                                'N/A'}
                            </td>
                            <td className="px-3 py-2 font-mono text-xs text-gray-600">{game.game_id}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ))}
              {Object.keys(boxscore_cache.games_by_season).length === 0 && (
                <p className="text-gray-500 text-center py-4">No games cached</p>
              )}
            </div>
          )}
        </div>

        {/* Team Schedules by Season */}
        <div className="card p-6 mb-6">
          <button
            onClick={() => toggleSection('schedules')}
            className="w-full flex items-center justify-between mb-4 hover:bg-gray-50 -m-2 p-2 rounded transition-colors"
          >
            <h2 className="text-xl font-semibold text-neutral-900">
              Team Schedules ({schedule_cache.total_schedules} total)
            </h2>
            <svg 
              className={`w-5 h-5 transition-transform ${expandedSections['schedules'] ? 'rotate-180' : ''}`}
              fill="none" 
              stroke="currentColor" 
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </button>

          {expandedSections['schedules'] && (
            <div className="space-y-4">
              {Object.entries(schedule_cache.schedules_by_season).map(([season, schedules]) => (
                <div key={season} className="border border-gray-200 rounded-lg p-4">
                  <h3 className="font-semibold text-gray-900 mb-3">
                    Season {season} ({schedules.length} teams)
                  </h3>
                  <div className="max-h-96 overflow-y-auto">
                    <table className="min-w-full text-sm">
                      <thead className="bg-gray-50 sticky top-0">
                        <tr>
                          <th className="px-3 py-2 text-left text-xs font-medium text-gray-700 uppercase">Team ID</th>
                          <th className="px-3 py-2 text-left text-xs font-medium text-gray-700 uppercase">Games</th>
                          <th className="px-3 py-2 text-left text-xs font-medium text-gray-700 uppercase">Filename</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-200">
                        {schedules.map((schedule: ScheduleFileInfo) => (
                          <tr key={schedule.filename} className="hover:bg-gray-50">
                            <td className="px-3 py-2 font-semibold text-gray-900">{schedule.team_id}</td>
                            <td className="px-3 py-2 text-gray-700">{schedule.games_count}</td>
                            <td className="px-3 py-2 font-mono text-xs text-gray-600">{schedule.filename}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ))}
              {Object.keys(schedule_cache.schedules_by_season).length === 0 && (
                <p className="text-gray-500 text-center py-4">No schedules cached</p>
              )}
            </div>
          )}
        </div>

        {/* Player Index Files */}
        <div className="card p-6 mb-6">
          <button
            onClick={() => toggleSection('player-files')}
            className="w-full flex items-center justify-between mb-4 hover:bg-gray-50 -m-2 p-2 rounded transition-colors"
          >
            <h2 className="text-xl font-semibold text-neutral-900">
              Player Index Files ({boxscore_cache.player_files_count} total)
            </h2>
            <svg 
              className={`w-5 h-5 transition-transform ${expandedSections['player-files'] ? 'rotate-180' : ''}`}
              fill="none" 
              stroke="currentColor" 
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </button>

          {expandedSections['player-files'] && (
            <div>
              <p className="text-sm text-gray-600 mb-3">
                Showing first {boxscore_cache.player_files.length} of {boxscore_cache.player_files_count} files
              </p>
              <div className="max-h-96 overflow-y-auto bg-gray-50 rounded-lg p-4">
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
                  {boxscore_cache.player_files.map((filename: string) => (
                    <div key={filename} className="font-mono text-xs text-gray-700 truncate">
                      {filename}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Season Stats Files */}
        <div className="card p-6 mb-6">
          <button
            onClick={() => toggleSection('season-stats')}
            className="w-full flex items-center justify-between mb-4 hover:bg-gray-50 -m-2 p-2 rounded transition-colors"
          >
            <h2 className="text-xl font-semibold text-neutral-900">Season Stats Files</h2>
            <svg 
              className={`w-5 h-5 transition-transform ${expandedSections['season-stats'] ? 'rotate-180' : ''}`}
              fill="none" 
              stroke="currentColor" 
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </button>

          {expandedSections['season-stats'] && (
            <div className="space-y-4">
              {Object.entries(boxscore_cache.season_stats_by_season).map(([season, playerStats]) => {
                const filteredPlayers = playerStats.filter((player: PlayerSeasonStats) =>
                  player.player_name.toLowerCase().includes(playerSearchTerm.toLowerCase())
                );

                return (
                  <div key={season} className="border border-gray-200 rounded-lg p-4">
                    <h3 className="font-semibold text-gray-900 mb-3">
                      Season {season} ({playerStats.length} players)
                    </h3>
                    
                    {/* Search input */}
                    <div className="mb-3">
                      <input
                        type="text"
                        placeholder="Search players..."
                        value={playerSearchTerm}
                        onChange={(e) => setPlayerSearchTerm(e.target.value)}
                        className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                      />
                    </div>

                    <div className="max-h-96 overflow-y-auto">
                      <table className="min-w-full text-sm">
                        <thead className="bg-gray-50 sticky top-0">
                          <tr>
                            <th className="px-3 py-2 text-left text-xs font-medium text-gray-700 uppercase">Player</th>
                            <th className="px-3 py-2 text-left text-xs font-medium text-gray-700 uppercase">ID</th>
                            <th className="px-3 py-2 text-left text-xs font-medium text-gray-700 uppercase">PPG</th>
                            <th className="px-3 py-2 text-left text-xs font-medium text-gray-700 uppercase">RPG</th>
                            <th className="px-3 py-2 text-left text-xs font-medium text-gray-700 uppercase">APG</th>
                            <th className="px-3 py-2 text-left text-xs font-medium text-gray-700 uppercase">GP</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-200">
                          {filteredPlayers.map((player: PlayerSeasonStats) => (
                            <tr 
                              key={player.filename}
                              onClick={() => setSelectedPlayer(player)}
                              className="hover:bg-blue-50 cursor-pointer"
                            >
                              <td className="px-3 py-2 font-medium text-blue-600 hover:text-blue-800">
                                {player.player_name}
                              </td>
                              <td className="px-3 py-2 text-gray-600 text-xs font-mono">{player.player_id}</td>
                              <td className="px-3 py-2 text-gray-900">{player.stats.points?.toFixed(1) || 'N/A'}</td>
                              <td className="px-3 py-2 text-gray-900">{player.stats.rebounds?.toFixed(1) || 'N/A'}</td>
                              <td className="px-3 py-2 text-gray-900">{player.stats.assists?.toFixed(1) || 'N/A'}</td>
                              <td className="px-3 py-2 text-gray-900">{player.stats.games_played || 'N/A'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      {filteredPlayers.length === 0 && (
                        <p className="text-gray-500 text-center py-4">No players match your search</p>
                      )}
                    </div>
                  </div>
                );
              })}
              {Object.keys(boxscore_cache.season_stats_by_season).length === 0 && (
                <p className="text-gray-500 text-center py-4">No season stats cached</p>
              )}
            </div>
          )}
        </div>

        {/* Refresh Button */}
        <div className="flex justify-center">
          <button
            onClick={loadCacheData}
            className="px-6 py-3 bg-neutral-900 text-white rounded-xl hover:bg-neutral-800 transition-colors font-medium"
          >
            Refresh Cache Data
          </button>
        </div>

        {/* Game Box Score Modal */}
        {selectedGame && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50" onClick={closeGameModal}>
            <div className="bg-white rounded-xl max-w-6xl w-full max-h-[90vh] overflow-hidden" onClick={(e) => e.stopPropagation()}>
              <div className="p-6 border-b border-gray-200 flex items-center justify-between sticky top-0 bg-white">
                <div>
                  <h3 className="text-2xl font-bold text-neutral-900">
                    {selectedGame.away_team} @ {selectedGame.home_team}
                  </h3>
                  <p className="text-gray-600 mt-1">
                    {selectedGame.game_date} • Final: {selectedGame.away_score} - {selectedGame.home_score}
                  </p>
                </div>
                <button
                  onClick={closeGameModal}
                  className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
                >
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
              <div className="p-6 overflow-y-auto max-h-[calc(90vh-120px)]">
                {selectedGame.box_score && Object.keys(selectedGame.box_score).length > 0 ? (
                  <div className="overflow-x-auto">
                    <table className="min-w-full text-sm">
                      <thead className="bg-gray-50 sticky top-0">
                        <tr>
                          <th className="px-3 py-2 text-left text-xs font-medium text-gray-700 uppercase">Player</th>
                          <th className="px-3 py-2 text-center text-xs font-medium text-gray-700 uppercase">MIN</th>
                          <th className="px-3 py-2 text-center text-xs font-medium text-gray-700 uppercase">PTS</th>
                          <th className="px-3 py-2 text-center text-xs font-medium text-gray-700 uppercase">REB</th>
                          <th className="px-3 py-2 text-center text-xs font-medium text-gray-700 uppercase">AST</th>
                          <th className="px-3 py-2 text-center text-xs font-medium text-gray-700 uppercase">STL</th>
                          <th className="px-3 py-2 text-center text-xs font-medium text-gray-700 uppercase">BLK</th>
                          <th className="px-3 py-2 text-center text-xs font-medium text-gray-700 uppercase">TO</th>
                          <th className="px-3 py-2 text-center text-xs font-medium text-gray-700 uppercase">FG</th>
                          <th className="px-3 py-2 text-center text-xs font-medium text-gray-700 uppercase">3PT</th>
                          <th className="px-3 py-2 text-center text-xs font-medium text-gray-700 uppercase">FT</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-200">
                        {Object.entries(selectedGame.box_score).map(([playerId, stats]: [string, any]) => (
                          <tr key={playerId} className="hover:bg-gray-50">
                            <td className="px-3 py-2 font-medium text-gray-900">
                              {stats.PLAYER_NAME || `Player ${playerId}`}
                            </td>
                            <td className="px-3 py-2 text-center text-gray-700">{stats.MIN || 0}</td>
                            <td className="px-3 py-2 text-center text-gray-900 font-semibold">{stats.PTS || 0}</td>
                            <td className="px-3 py-2 text-center text-gray-700">{stats.REB || 0}</td>
                            <td className="px-3 py-2 text-center text-gray-700">{stats.AST || 0}</td>
                            <td className="px-3 py-2 text-center text-gray-700">{stats.STL || 0}</td>
                            <td className="px-3 py-2 text-center text-gray-700">{stats.BLK || 0}</td>
                            <td className="px-3 py-2 text-center text-gray-700">{stats.TO || 0}</td>
                            <td className="px-3 py-2 text-center text-gray-700 text-xs">
                              {stats.FGM || 0}/{stats.FGA || 0}
                            </td>
                            <td className="px-3 py-2 text-center text-gray-700 text-xs">
                              {stats.FG3M || 0}/{stats.FG3A || 0}
                            </td>
                            <td className="px-3 py-2 text-center text-gray-700 text-xs">
                              {stats.FTM || 0}/{stats.FTA || 0}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p className="text-gray-500 text-center py-8">No box score data available</p>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Player Stats Modal */}
        {selectedPlayer && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50" onClick={closePlayerModal}>
            <div className="bg-white rounded-xl max-w-2xl w-full max-h-[90vh] overflow-hidden" onClick={(e) => e.stopPropagation()}>
              <div className="p-6 border-b border-gray-200 flex items-center justify-between sticky top-0 bg-white">
                <div>
                  <h3 className="text-2xl font-bold text-neutral-900">{selectedPlayer.player_name}</h3>
                  <p className="text-gray-600 mt-1">Player ID: {selectedPlayer.player_id}</p>
                </div>
                <button
                  onClick={closePlayerModal}
                  className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
                >
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
              <div className="p-6 overflow-y-auto max-h-[calc(90vh-120px)]">
                <div className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    {Object.entries(selectedPlayer.stats).map(([stat, value]) => (
                      <div key={stat} className="bg-gray-50 rounded-lg p-4">
                        <div className="text-xs text-gray-600 uppercase mb-1">
                          {stat.replace(/_/g, ' ')}
                        </div>
                        <div className="text-2xl font-bold text-neutral-900">
                          {typeof value === 'number' ? value.toFixed(2) : value}
                        </div>
                      </div>
                    ))}
                  </div>
                  <div className="mt-4 pt-4 border-t border-gray-200">
                    <div className="text-xs text-gray-600">Last Updated</div>
                    <div className="text-sm text-gray-900 mt-1">
                      {selectedPlayer.last_updated ? new Date(selectedPlayer.last_updated).toLocaleString() : 'N/A'}
                    </div>
                  </div>
                  <div className="mt-2">
                    <div className="text-xs text-gray-600">Filename</div>
                    <div className="text-xs font-mono text-gray-700 bg-gray-100 p-2 rounded mt-1 break-all">
                      {selectedPlayer.filename}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </Layout>
  );
}
