/**
 * Box score table component for displaying team player stats
 */

import { StatCell } from './StatCell';
import type { PlayerBoxScore } from '../types/api';

interface BoxScoreTableProps {
  players: PlayerBoxScore[];
  teamTricode?: string;
  gameId?: string;
  onPlayerClick?: (playerId: number, playerName: string) => void;
  onInspectPlayer?: (playerId: number, playerName: string, gameId: string) => void;
}

export function BoxScoreTable({ players, gameId, onPlayerClick, onInspectPlayer }: BoxScoreTableProps) {
  // Sort players by minutes played (descending)
  const sortedPlayers = [...players].sort((a, b) => {
    const minsA = parseFloat(a.MIN || '0');
    const minsB = parseFloat(b.MIN || '0');
    return minsB - minsA;
  });

  return (
    <div className="overflow-x-auto touch-scroll">
      <table className="min-w-full text-xs">
        <thead>
          <tr className="border-b border-gray-300 bg-gray-50">
            <th className="sticky left-0 z-10 bg-gray-50 px-2 py-2 text-left font-semibold text-gray-700 shadow-[2px_0_4px_-2px_rgba(0,0,0,0.1)]">
              Player
            </th>
            <th className="px-2 py-2 text-right font-semibold text-gray-700">MIN</th>
            <th className="px-2 py-2 text-right font-semibold text-gray-700">FGM-A</th>
            <th className="px-2 py-2 text-right font-semibold text-gray-700">FG%</th>
            <th className="px-2 py-2 text-right font-semibold text-gray-700">3PM-A</th>
            <th className="px-2 py-2 text-right font-semibold text-gray-700">3P%</th>
            <th className="px-2 py-2 text-right font-semibold text-gray-700">FTM-A</th>
            <th className="px-2 py-2 text-right font-semibold text-gray-700">FT%</th>
            <th className="px-2 py-2 text-right font-semibold text-gray-700">PTS</th>
            <th className="px-2 py-2 text-right font-semibold text-gray-700">REB</th>
            <th className="px-2 py-2 text-right font-semibold text-gray-700">AST</th>
            <th className="px-2 py-2 text-right font-semibold text-gray-700">STL</th>
            <th className="px-2 py-2 text-right font-semibold text-gray-700">BLK</th>
            <th className="px-2 py-2 text-right font-semibold text-gray-700">TO</th>
            <th className="px-2 py-2 text-right font-semibold text-gray-700">PF</th>
            <th className="px-2 py-2 text-right font-semibold text-gray-700">USG%</th>
            <th className="px-2 py-2 text-right font-semibold text-gray-700">+/-</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-200">
          {sortedPlayers.map((player, index) => {
            // First 5 players are starters - highlight them
            const isStarter = index < 5;
            const rowClass = isStarter 
              ? 'bg-blue-50 hover:bg-blue-100' 
              : 'hover:bg-gray-50';
            const nameClass = isStarter
              ? 'sticky left-0 z-10 bg-blue-50 hover:bg-blue-100 px-2 py-2 text-left font-bold text-gray-900 shadow-[2px_0_4px_-2px_rgba(0,0,0,0.1)]'
              : 'sticky left-0 z-10 bg-white hover:bg-gray-50 px-2 py-2 text-left font-medium text-gray-900 shadow-[2px_0_4px_-2px_rgba(0,0,0,0.1)]';

            return (
              <tr key={player.PLAYER_ID} className={rowClass}>
                <td className={nameClass}>
                  <div className="flex items-center gap-1">
                    {onPlayerClick ? (
                      <button
                        onClick={() => onPlayerClick(player.PLAYER_ID, player.PLAYER_NAME)}
                        className="hover:text-cyan-600 hover:underline cursor-pointer text-left transition-colors flex-1"
                      >
                        {player.PLAYER_NAME}
                      </button>
                    ) : (
                      <span className="flex-1">{player.PLAYER_NAME}</span>
                    )}
                    {onInspectPlayer && gameId && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onInspectPlayer(player.PLAYER_ID, player.PLAYER_NAME, gameId);
                        }}
                        className="p-1 rounded hover:bg-gray-200 text-gray-400 hover:text-gray-700 transition-colors flex-shrink-0"
                        title="Inspect performance (play-by-play analysis)"
                      >
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                        </svg>
                      </button>
                    )}
                  </div>
                </td>
                <td className="px-2 py-2 text-right text-gray-900">
                  {player.MIN || '0'}
                </td>
                <td className="px-2 py-2 text-right text-gray-900">
                  {player.FGM !== null && player.FGA !== null
                    ? `${player.FGM}-${player.FGA}`
                    : '-'}
                </td>
                <StatCell
                  statName="fg_pct"
                  value={player.FG_PCT || 0}
                  attempts={{ made: player.FGM || 0, attempts: player.FGA || 0 }}
                />
                <td className="px-2 py-2 text-right text-gray-900">
                  {player.FG3M !== null && player.FG3A !== null
                    ? `${player.FG3M}-${player.FG3A}`
                    : '-'}
                </td>
                <StatCell
                  statName="fg3_pct"
                  value={player.FG3_PCT || 0}
                  attempts={{ made: player.FG3M || 0, attempts: player.FG3A || 0 }}
                />
                <td className="px-2 py-2 text-right text-gray-900">
                  {player.FTM !== null && player.FTA !== null
                    ? `${player.FTM}-${player.FTA}`
                    : '-'}
                </td>
                <StatCell
                  statName="ft_pct"
                  value={player.FT_PCT || 0}
                  attempts={{ made: player.FTM || 0, attempts: player.FTA || 0 }}
                />
                <StatCell
                  statName="points"
                  value={player.PTS || 0}
                />
                <StatCell
                  statName="rebounds"
                  value={player.REB || 0}
                />
                <StatCell
                  statName="assists"
                  value={player.AST || 0}
                />
                <StatCell
                  statName="steals"
                  value={player.STL || 0}
                />
                <StatCell
                  statName="blocks"
                  value={player.BLK || 0}
                />
                <StatCell
                  statName="turnovers"
                  value={player.TO || 0}
                />
                <td className="px-2 py-2 text-right text-gray-900">
                  {player.PF ?? '-'}
                </td>
                <StatCell
                  statName="USG%"
                  value={player.USG_PCT || 0}
                />
                <StatCell
                  statName="PLUS_MINUS"
                  value={player.PLUS_MINUS || 0}
                />
              </tr>
            );
          })}
        </tbody>
      </table>
      {sortedPlayers.length === 0 && (
        <div className="py-8 text-center text-gray-500">
          No player data available
        </div>
      )}
    </div>
  );
}

