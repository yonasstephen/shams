/**
 * Reusable player stats table component
 */

import type { PlayerStats } from '../types/api';
import { StatCell } from './StatCell';

interface PlayerTableProps {
  periods: {
    name: string;
    stats: PlayerStats | null;
  }[];
  playerName: string;
  playerId: number;
}

export function PlayerTable({ periods, playerName, playerId }: PlayerTableProps) {
  return (
    <div className="card overflow-hidden">
      <div className="px-4 md:px-6 py-4 md:py-5 border-b border-gray-200">
        <h2 className="text-lg md:text-2xl font-bold text-neutral-900">
          {playerName} <span className="text-gray-500 text-sm md:text-lg font-normal">(ID {playerId})</span>
        </h2>
      </div>

      <div className="overflow-x-auto touch-scroll">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-neutral-50">
            <tr>
              <th className="sticky left-0 z-10 bg-neutral-50 px-3 md:px-4 py-2 md:py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider shadow-[2px_0_4px_-2px_rgba(0,0,0,0.1)]">
                Period
              </th>
              <th className="px-2 md:px-4 py-2 md:py-3 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">
                FG%
              </th>
              <th className="px-2 md:px-4 py-2 md:py-3 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">
                FT%
              </th>
              <th className="px-2 md:px-4 py-2 md:py-3 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">
                3PM
              </th>
              <th className="px-2 md:px-4 py-2 md:py-3 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">
                PTS
              </th>
              <th className="px-2 md:px-4 py-2 md:py-3 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">
                REB
              </th>
              <th className="px-2 md:px-4 py-2 md:py-3 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">
                AST
              </th>
              <th className="px-2 md:px-4 py-2 md:py-3 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">
                STL
              </th>
              <th className="px-2 md:px-4 py-2 md:py-3 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">
                BLK
              </th>
              <th className="px-2 md:px-4 py-2 md:py-3 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">
                TO
              </th>
              <th className="px-2 md:px-4 py-2 md:py-3 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">
                USG%
              </th>
              <th className="px-2 md:px-4 py-2 md:py-3 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">
                Starter
              </th>
              <th className="px-2 md:px-4 py-2 md:py-3 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">
                MIN
              </th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-100">
            {periods.map((period) => {
              // Use 'last' mode for "Last Game", 'avg' mode for averaged periods
              const aggMode = period.name === 'Last Game' ? 'last' : 'avg';
              
              return (
                <tr key={period.name} className="hover:bg-neutral-50 transition-colors">
                  <td className="sticky left-0 z-10 bg-white group-hover:bg-neutral-50 px-3 md:px-4 py-2 md:py-3 whitespace-nowrap text-xs md:text-sm font-medium text-cyan-600 shadow-[2px_0_4px_-2px_rgba(0,0,0,0.1)]">
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
                    <td className="px-2 md:px-4 py-2 md:py-3 text-right text-xs md:text-sm text-neutral-900">
                      {period.name === 'Last Game'
                        ? period.stats.games_started === 1
                          ? '✓'
                          : ''
                        : period.stats.games_started}
                    </td>
                    <StatCell statName="MIN" value={period.stats.minutes} aggMode={aggMode} />
                  </>
                ) : (
                  <td colSpan={12} className="px-2 md:px-4 py-2 md:py-3 text-center text-xs md:text-sm text-gray-500">
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
  );
}

