/**
 * Remaining Days Projection component
 * Shows projected stats for each player for each remaining day of the week
 */

import { StatCell } from './StatCell';
import type { PlayerContribution } from '../types/api';

type SortField = 'name' | 'games' | string; // string for stat IDs
type SortDirection = 'asc' | 'desc';

interface RemainingDaysProjectionProps {
  remaining_days_projection: Record<string, Record<string, Record<string, number>>>;
  stat_categories: any[];
  player_contributions: PlayerContribution[];
  current_player_contributions: PlayerContribution[];
  player_positions: Record<string, Record<string, string>>;
  week_start: string;
  week_end: string;
  title?: string;
  onPlayerClick?: (playerId: number, playerName: string) => void;
  // Sort props
  sortField: SortField;
  sortDirection: SortDirection;
  onSort: (field: SortField) => void;
}

export function RemainingDaysProjection({
  remaining_days_projection,
  stat_categories,
  player_contributions,
  current_player_contributions,
  player_positions,
  week_start,
  week_end,
  title = "Remaining Games Projection",
  onPlayerClick,
  sortField,
  sortDirection,
  onSort,
}: RemainingDaysProjectionProps) {
  // Parse date range and filter to remaining dates (today onwards)
  const startDate = new Date(week_start);
  const endDate = new Date(week_end);
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const remainingDates: string[] = [];
  const current = new Date(Math.max(startDate.getTime(), today.getTime()));
  
  while (current <= endDate) {
    remainingDates.push(current.toISOString().split('T')[0]);
    current.setDate(current.getDate() + 1);
  }

  if (remainingDates.length === 0) {
    return null;
  }

  // Filter to get the 9 main stats (same logic as in Matchup.tsx)
  const mainStats = stat_categories
    .filter((stat: any) => {
      const statId = String(stat.stat_id);
      const statName = stat.display_name || stat.name || '';
      // Filter out FGM/A and FTM/A columns (redundant with FG% and FT%)
      return statId !== '9004003' && statId !== '9007006' && !statName.includes('M/A');
    })
    .slice(0, 9);

  // Sort players: first by roster status (on roster first), then by selected field
  const sortedPlayers = [...player_contributions].sort((a, b) => {
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

  // Format date header
  const formatDateHeader = (dateStr: string): string => {
    const date = new Date(dateStr + 'T00:00:00');
    const dayName = date.toLocaleDateString('en-US', { weekday: 'short' });
    const month = date.getMonth() + 1;
    const day = date.getDate();
    return `${dayName} ${month}/${day}`;
  };

  // Sort indicator component
  const SortIcon = ({ field }: { field: SortField }) => {
    if (sortField !== field) {
      return <span className="text-gray-400 ml-1">↕</span>;
    }
    return <span className="text-gray-900 ml-1">{sortDirection === 'asc' ? '↑' : '↓'}</span>;
  };

  // Calculate totals for each stat category
  const calculateTotals = () => {
    const totals: Record<string, number> = {};
    let totalFGM = 0;
    let totalFGA = 0;
    let totalFTM = 0;
    let totalFTA = 0;

    // Sum up stats from all players who are on the roster
    sortedPlayers.forEach((contrib) => {
      if (!contrib.is_on_roster_today) return; // Skip players not on roster
      
      const playerStats = contrib.stats || {};
      const playerShooting = contrib.shooting || {};
      
      mainStats.forEach((stat: any) => {
        const statId = String(stat.stat_id);
        const value = playerStats[statId] ?? 0;
        
        if (!totals[statId]) {
          totals[statId] = 0;
        }
        totals[statId] += value;
      });
      
      // Accumulate shooting stats for percentage calculations
      totalFGM += playerShooting?.fgm ?? 0;
      totalFGA += playerShooting?.fga ?? 0;
      totalFTM += playerShooting?.ftm ?? 0;
      totalFTA += playerShooting?.fta ?? 0;
    });

    return { totals, totalFGM, totalFGA, totalFTM, totalFTA };
  };

  const { totals, totalFGM, totalFGA, totalFTM, totalFTA } = calculateTotals();

  // Calculate game counts from player contributions
  const calculateGameCounts = () => {
    let gamesPlayed = 0;
    let remainingGames = 0;
    let totalGames = 0;

    // Games played comes from current_player_contributions (actual stats so far)
    // Count ALL games played, even from players no longer on roster (those games already happened)
    current_player_contributions.forEach((contrib) => {
      gamesPlayed += contrib.games_played || 0;
    });

    // Remaining games comes from player_contributions (projected stats)
    // Only count players currently on roster for future projections
    sortedPlayers.forEach((contrib) => {
      if (!contrib.is_on_roster_today) return; // Skip players not on roster
      remainingGames += contrib.remaining_games || 0;
      totalGames += contrib.total_games || 0;
    });

    return { gamesPlayed, remainingGames, totalGames };
  };

  const { gamesPlayed, remainingGames: totalRemainingGames, totalGames } = calculateGameCounts();

  return (
    <div className="bg-white rounded-lg shadow-md overflow-hidden">
      <div className="p-6 pb-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
        <h3 className="text-xl font-semibold text-gray-900">
          {title}
        </h3>
        <div className="flex items-center gap-3 text-sm">
          <div className="flex items-center gap-1.5">
            <span className="text-gray-500">Played:</span>
            <span className="font-semibold text-cyan-600">{gamesPlayed}</span>
          </div>
          <span className="text-gray-300">|</span>
          <div className="flex items-center gap-1.5">
            <span className="text-gray-500">Remaining:</span>
            <span className="font-semibold text-emerald-600">{totalRemainingGames}</span>
          </div>
          <span className="text-gray-300">|</span>
          <div className="flex items-center gap-1.5">
            <span className="text-gray-500">Total:</span>
            <span className="font-semibold text-gray-900">{totalGames}</span>
          </div>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th 
                className="px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider sticky left-0 bg-gray-50 z-10 cursor-pointer hover:bg-gray-100 transition-colors select-none"
                onClick={() => onSort('name')}
              >
                <div className="flex items-center">
                  Player
                  <SortIcon field="name" />
                </div>
              </th>
              {mainStats.map((stat: any) => {
                const statId = String(stat.stat_id);
                return (
                  <th 
                    key={statId}
                    className="px-3 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100 transition-colors select-none"
                    onClick={() => onSort(statId)}
                  >
                    <div className="flex items-center justify-end">
                      {stat.abbr || stat.display_name}
                      <SortIcon field={statId} />
                    </div>
                  </th>
                );
              })}
              {remainingDates.map((dateStr) => (
                <th
                  key={dateStr}
                  className="px-3 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider"
                >
                  <div className="whitespace-pre-line">
                    {formatDateHeader(dateStr)}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {sortedPlayers.map((contrib) => {
              // Ensure stats and shooting are defined
              const playerStats = contrib.stats || {};
              const playerShooting = contrib.shooting || {};
              
              // Apply gray color to players no longer on roster
              const playerNameColor = contrib.is_on_roster_today ? 'text-gray-900' : 'text-gray-400';

              return (
                <tr key={contrib.player_key} className="hover:bg-gray-50">
                  <td className="px-3 py-2 whitespace-nowrap text-sm font-medium sticky left-0 bg-white z-10">
                    {contrib.player_id && onPlayerClick ? (
                      <button
                        onClick={() => onPlayerClick(contrib.player_id!, contrib.player_name)}
                        className="text-cyan-600 hover:text-cyan-700 hover:underline transition-colors cursor-pointer text-left"
                      >
                        {contrib.player_name}
                      </button>
                    ) : (
                      <span className={playerNameColor}>{contrib.player_name}</span>
                    )}
                  </td>
                  {mainStats.map((stat: any) => {
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
                            aggMode="last"
                          />
                        );
                      } else if (statId === '8' && (ftm > 0 || fta > 0)) {
                        return (
                          <StatCell
                            key={statId}
                            statName="FT%"
                            value={value}
                            attempts={{ made: ftm, attempts: fta }}
                            aggMode="last"
                          />
                        );
                      } else {
                        return (
                          <StatCell
                            key={statId}
                            statName={statName}
                            value={value}
                            aggMode="last"
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
                        aggMode="last"
                      />
                    );
                  })}
                  {remainingDates.map((dateStr) => {
                    const hasGame = remaining_days_projection[contrib.player_key]?.[dateStr];
                    const position = player_positions[contrib.player_key]?.[dateStr] || '';
                    
                    // Check if player has a game but is in an inactive position
                    const inactivePositions = ['IL', 'IL+', 'BN'];
                    const isInactive = inactivePositions.includes(position);
                    
                    return (
                      <td key={dateStr} className="px-3 py-2 text-center text-sm">
                        {hasGame ? (
                          isInactive ? (
                            <span className="text-orange-600 font-semibold">{position}</span>
                          ) : (
                            <span className="text-green-600">✓</span>
                          )
                        ) : (
                          <span className="text-gray-300">-</span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
            {/* Totals Row */}
            <tr className="bg-gray-100 border-t-2 border-gray-300 font-semibold">
              <td className="px-3 py-3 whitespace-nowrap text-sm sticky left-0 bg-gray-100 z-10">
                <span className="text-gray-900 font-bold">Total</span>
              </td>
              {mainStats.map((stat: any) => {
                const statId = String(stat.stat_id);
                const value = totals[statId] ?? 0;
                const statName = stat.display_name || stat.name || '';

                if (statName.includes('%')) {
                  // For FG%, calculate from total FGM/FGA
                  if (statId === '5') {
                    const fgPct = totalFGA > 0 ? (totalFGM / totalFGA) * 100 : 0;
                    return (
                      <td key={statId} className="px-3 py-3 text-right text-sm">
                        <div>
                          <div className="font-bold text-gray-900">
                            {fgPct.toFixed(1)}%
                          </div>
                          <div className="text-xs text-gray-600">
                            ({totalFGM.toFixed(0)}/{totalFGA.toFixed(0)})
                          </div>
                        </div>
                      </td>
                    );
                  }
                  // For FT%, calculate from total FTM/FTA
                  else if (statId === '8') {
                    const ftPct = totalFTA > 0 ? (totalFTM / totalFTA) * 100 : 0;
                    return (
                      <td key={statId} className="px-3 py-3 text-right text-sm">
                        <div>
                          <div className="font-bold text-gray-900">
                            {ftPct.toFixed(1)}%
                          </div>
                          <div className="text-xs text-gray-600">
                            ({totalFTM.toFixed(0)}/{totalFTA.toFixed(0)})
                          </div>
                        </div>
                      </td>
                    );
                  }
                  // For other percentages (shouldn't happen, but handle gracefully)
                  return (
                    <td key={statId} className="px-3 py-3 text-right text-sm font-bold text-gray-900">
                      {value.toFixed(1)}%
                    </td>
                  );
                }

                // For non-percentage stats, just show the sum
                // Determine if we should show decimal places
                const displayValue = Number.isInteger(value) ? value.toString() : value.toFixed(1);
                
                return (
                  <td key={statId} className="px-3 py-3 text-right text-sm font-bold text-gray-900">
                    {displayValue}
                  </td>
                );
              })}
              {/* Empty cells for the date columns */}
              {remainingDates.map((dateStr) => (
                <td key={dateStr} className="px-3 py-3 text-center text-sm">
                  <span className="text-gray-400">-</span>
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}

