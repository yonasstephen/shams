/**
 * Top Performers Panel - displays top performers for a given date
 * Shows tabbed interface with different stat categories
 * Includes 9-cat fantasy value ranking using z-scores
 */

import { useState, useEffect } from 'react';
import type { GameBoxScore, PlayerBoxScore } from '../types/api';

// Z-score calculation utility functions
function calculateMean(values: number[]): number {
  if (values.length === 0) return 0;
  return values.reduce((a, b) => a + b, 0) / values.length;
}

function calculateStdDev(values: number[], mean: number): number {
  if (values.length === 0) return 1;
  const variance = values.reduce((sum, val) => sum + Math.pow(val - mean, 2), 0) / values.length;
  return Math.sqrt(variance) || 1; // Prevent division by zero
}

function calculateZScore(value: number, mean: number, stdDev: number): number {
  return (value - mean) / stdDev;
}

// Z-scores for each of the 9 fantasy categories
interface ZScores {
  fg: number;   // FG% impact (volume-adjusted)
  ft: number;   // FT% impact (volume-adjusted)
  threes: number;
  pts: number;
  reb: number;
  ast: number;
  stl: number;
  blk: number;
  to: number;
}

interface TopPerformer {
  playerId: number;
  playerName: string;
  teamTricode: string;
  statValue: number;
  minutes: string;
  // For FGA/FTA categories
  made?: number;
  percentage?: number;
  // Full stat line
  pts: number;
  reb: number;
  ast: number;
  stl: number;
  blk: number;
  to: number;
  fgm: number;
  fga: number;
  fg3m: number;
  ftm: number;
  fta: number;
  // 9-cat fantasy value fields
  fantasyValue?: number;
  zScores?: ZScores;
  // FG/FT impact values (makes above average)
  fgImpact?: number;
  ftImpact?: number;
}

// Population statistics for z-score calculation
interface PopulationStats {
  // Counting stats
  threes: { mean: number; stdDev: number };
  pts: { mean: number; stdDev: number };
  reb: { mean: number; stdDev: number };
  ast: { mean: number; stdDev: number };
  stl: { mean: number; stdDev: number };
  blk: { mean: number; stdDev: number };
  to: { mean: number; stdDev: number };
  // Percentage impact stats
  fgImpact: { mean: number; stdDev: number };
  ftImpact: { mean: number; stdDev: number };
  // League averages for percentage calculations
  avgFgPct: number;
  avgFtPct: number;
}

interface TopPerformersPanelProps {
  games: GameBoxScore[];
  onPlayerClick?: (playerId: number, playerName: string) => void;
  /** Hide middle stats section for narrow layouts (e.g., BoxScores page sidebar) */
  compact?: boolean;
}

type StatCategory = {
  id: string;
  label: string;
  limit: number;
  statKey: keyof PlayerBoxScore | 'fantasyValue';
  isBadStat?: boolean;
  isComposite?: boolean;
};

const STAT_CATEGORIES: StatCategory[] = [
  { id: 'fantasy', label: '9-Cat', limit: 15, statKey: 'fantasyValue', isComposite: true },
  { id: 'pts', label: 'Points', limit: 10, statKey: 'PTS' },
  { id: 'reb', label: 'Rebounds', limit: 10, statKey: 'REB' },
  { id: 'ast', label: 'Assists', limit: 10, statKey: 'AST' },
  { id: 'stl', label: 'Steals', limit: 10, statKey: 'STL' },
  { id: 'blk', label: 'Blocks', limit: 10, statKey: 'BLK' },
  { id: 'fga', label: 'FG Attempts', limit: 10, statKey: 'FGA' },
  { id: 'fta', label: 'FT Attempts', limit: 10, statKey: 'FTA' },
  { id: 'to', label: 'Turnovers', limit: 5, statKey: 'TO', isBadStat: true },
];

/**
 * Calculate population statistics from all players for z-score normalization
 */
function calculatePopulationStats(players: PlayerBoxScore[]): PopulationStats {
  // Calculate league average FG% and FT% (total makes / total attempts)
  const totalFgm = players.reduce((sum, p) => sum + (p.FGM || 0), 0);
  const totalFga = players.reduce((sum, p) => sum + (p.FGA || 0), 0);
  const totalFtm = players.reduce((sum, p) => sum + (p.FTM || 0), 0);
  const totalFta = players.reduce((sum, p) => sum + (p.FTA || 0), 0);
  
  const avgFgPct = totalFga > 0 ? totalFgm / totalFga : 0.47; // Default to ~47% if no data
  const avgFtPct = totalFta > 0 ? totalFtm / totalFta : 0.78; // Default to ~78% if no data
  
  // Calculate FG/FT impact for each player (makes above average)
  const fgImpacts = players.map(p => {
    const fgm = p.FGM || 0;
    const fga = p.FGA || 0;
    return fgm - (fga * avgFgPct);
  });
  
  const ftImpacts = players.map(p => {
    const ftm = p.FTM || 0;
    const fta = p.FTA || 0;
    return ftm - (fta * avgFtPct);
  });
  
  // Calculate means and standard deviations for all categories
  const threesValues = players.map(p => p.FG3M || 0);
  const ptsValues = players.map(p => p.PTS || 0);
  const rebValues = players.map(p => p.REB || 0);
  const astValues = players.map(p => p.AST || 0);
  const stlValues = players.map(p => p.STL || 0);
  const blkValues = players.map(p => p.BLK || 0);
  const toValues = players.map(p => p.TO || 0);
  
  const threesMean = calculateMean(threesValues);
  const ptsMean = calculateMean(ptsValues);
  const rebMean = calculateMean(rebValues);
  const astMean = calculateMean(astValues);
  const stlMean = calculateMean(stlValues);
  const blkMean = calculateMean(blkValues);
  const toMean = calculateMean(toValues);
  const fgImpactMean = calculateMean(fgImpacts);
  const ftImpactMean = calculateMean(ftImpacts);
  
  return {
    threes: { mean: threesMean, stdDev: calculateStdDev(threesValues, threesMean) },
    pts: { mean: ptsMean, stdDev: calculateStdDev(ptsValues, ptsMean) },
    reb: { mean: rebMean, stdDev: calculateStdDev(rebValues, rebMean) },
    ast: { mean: astMean, stdDev: calculateStdDev(astValues, astMean) },
    stl: { mean: stlMean, stdDev: calculateStdDev(stlValues, stlMean) },
    blk: { mean: blkMean, stdDev: calculateStdDev(blkValues, blkMean) },
    to: { mean: toMean, stdDev: calculateStdDev(toValues, toMean) },
    fgImpact: { mean: fgImpactMean, stdDev: calculateStdDev(fgImpacts, fgImpactMean) },
    ftImpact: { mean: ftImpactMean, stdDev: calculateStdDev(ftImpacts, ftImpactMean) },
    avgFgPct,
    avgFtPct,
  };
}

/**
 * Calculate fantasy value and z-scores for a single player
 */
function calculateFantasyValue(
  player: PlayerBoxScore,
  popStats: PopulationStats
): { fantasyValue: number; zScores: ZScores; fgImpact: number; ftImpact: number } {
  // Calculate FG/FT impact (makes above average)
  const fgm = player.FGM || 0;
  const fga = player.FGA || 0;
  const ftm = player.FTM || 0;
  const fta = player.FTA || 0;
  
  const fgImpact = fgm - (fga * popStats.avgFgPct);
  const ftImpact = ftm - (fta * popStats.avgFtPct);
  
  // Calculate z-scores for all 9 categories
  const zScores: ZScores = {
    fg: calculateZScore(fgImpact, popStats.fgImpact.mean, popStats.fgImpact.stdDev),
    ft: calculateZScore(ftImpact, popStats.ftImpact.mean, popStats.ftImpact.stdDev),
    threes: calculateZScore(player.FG3M || 0, popStats.threes.mean, popStats.threes.stdDev),
    pts: calculateZScore(player.PTS || 0, popStats.pts.mean, popStats.pts.stdDev),
    reb: calculateZScore(player.REB || 0, popStats.reb.mean, popStats.reb.stdDev),
    ast: calculateZScore(player.AST || 0, popStats.ast.mean, popStats.ast.stdDev),
    stl: calculateZScore(player.STL || 0, popStats.stl.mean, popStats.stl.stdDev),
    blk: calculateZScore(player.BLK || 0, popStats.blk.mean, popStats.blk.stdDev),
    to: calculateZScore(player.TO || 0, popStats.to.mean, popStats.to.stdDev),
  };
  
  // Total fantasy value: sum of all z-scores, with TO subtracted (lower is better)
  const fantasyValue = 
    zScores.fg + 
    zScores.ft + 
    zScores.threes + 
    zScores.pts + 
    zScores.reb + 
    zScores.ast + 
    zScores.stl + 
    zScores.blk - 
    zScores.to;  // Subtract TO because lower is better
  
  return { fantasyValue, zScores, fgImpact, ftImpact };
}

export function TopPerformersPanel({ games, onPlayerClick, compact = false }: TopPerformersPanelProps) {
  const [activeTab, setActiveTab] = useState<string>('fantasy');
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [topPerformersByCategory, setTopPerformersByCategory] = useState<Record<string, TopPerformer[]>>({});

  // Calculate top performers when games change (lazy load)
  useEffect(() => {
    const calculateTopPerformers = () => {
      setIsLoading(true);
      
      // Use setTimeout to allow UI to update with loading state
      setTimeout(() => {
        const result: Record<string, TopPerformer[]> = {};

        // Collect all players from all games
        const allPlayers: PlayerBoxScore[] = [];
        games.forEach((game) => {
          if (game.box_score) {
            Object.values(game.box_score).forEach((player) => {
              // Only include players who actually played (have minutes)
              const minutes = parseFloat(player.MIN || '0');
              if (minutes > 0) {
                allPlayers.push(player);
              }
            });
          }
        });

        // Calculate population statistics for z-score normalization
        const popStats = calculatePopulationStats(allPlayers);

        // Calculate top performers for each category
        STAT_CATEGORIES.forEach((category) => {
          if (category.isComposite) {
            // Fantasy value category - calculate z-scores and sort by composite value
            const performersWithFantasy = allPlayers
              .map((player) => {
                const { fantasyValue, zScores, fgImpact, ftImpact } = calculateFantasyValue(player, popStats);
                return {
                  playerId: player.PLAYER_ID,
                  playerName: player.PLAYER_NAME,
                  teamTricode: player.teamTricode || '',
                  statValue: fantasyValue,
                  minutes: player.MIN || '0',
                  pts: player.PTS || 0,
                  reb: player.REB || 0,
                  ast: player.AST || 0,
                  stl: player.STL || 0,
                  blk: player.BLK || 0,
                  to: player.TO || 0,
                  fgm: player.FGM || 0,
                  fga: player.FGA || 0,
                  fg3m: player.FG3M || 0,
                  ftm: player.FTM || 0,
                  fta: player.FTA || 0,
                  fantasyValue,
                  zScores,
                  fgImpact,
                  ftImpact,
                };
              })
              .sort((a, b) => (b.fantasyValue || 0) - (a.fantasyValue || 0))
              .slice(0, category.limit);
            
            result[category.id] = performersWithFantasy;
          } else {
            // Regular stat category
            const sorted = [...allPlayers]
              .filter((player) => {
                const statValue = player[category.statKey as keyof PlayerBoxScore];
                return statValue != null && statValue !== 0;
              })
              .sort((a, b) => {
                const valueA = Number(a[category.statKey as keyof PlayerBoxScore]) || 0;
                const valueB = Number(b[category.statKey as keyof PlayerBoxScore]) || 0;
                return valueB - valueA;
              })
              .slice(0, category.limit)
              .map((player) => {
                const { fantasyValue, zScores, fgImpact, ftImpact } = calculateFantasyValue(player, popStats);
                const basePerformer: TopPerformer = {
                  playerId: player.PLAYER_ID,
                  playerName: player.PLAYER_NAME,
                  teamTricode: player.teamTricode || '',
                  statValue: Number(player[category.statKey as keyof PlayerBoxScore]) || 0,
                  minutes: player.MIN || '0',
                  // Full stat line
                  pts: player.PTS || 0,
                  reb: player.REB || 0,
                  ast: player.AST || 0,
                  stl: player.STL || 0,
                  blk: player.BLK || 0,
                  to: player.TO || 0,
                  fgm: player.FGM || 0,
                  fga: player.FGA || 0,
                  fg3m: player.FG3M || 0,
                  ftm: player.FTM || 0,
                  fta: player.FTA || 0,
                  fantasyValue,
                  zScores,
                  fgImpact,
                  ftImpact,
                };

                // Add shooting stats for FGA/FTA categories
                if (category.id === 'fga') {
                  return {
                    ...basePerformer,
                    made: player.FGM || 0,
                    percentage: player.FG_PCT || 0,
                  };
                } else if (category.id === 'fta') {
                  return {
                    ...basePerformer,
                    made: player.FTM || 0,
                    percentage: player.FT_PCT || 0,
                  };
                }

                return basePerformer;
              });

            result[category.id] = sorted;
          }
        });

        setTopPerformersByCategory(result);
        setIsLoading(false);
      }, 0);
    };

    calculateTopPerformers();
  }, [games]);

  const activeCategory = STAT_CATEGORIES.find((cat) => cat.id === activeTab);
  const activePerformers = topPerformersByCategory[activeTab] || [];

  return (
    <div className="card bg-white sticky top-4">
      <div className="p-4 border-b border-gray-200">
        <h2 className="text-xl font-bold text-gray-900">Top Performers</h2>
        <p className="text-sm text-gray-600 mt-1">Best performances of the day</p>
      </div>

      {/* Tab Navigation */}
      <div className="border-b border-gray-200">
        <div className="flex flex-wrap">
          {STAT_CATEGORIES.map((category) => {
            const isActive = activeTab === category.id;
            const isBadStat = category.isBadStat;
            const isComposite = category.isComposite;
            
            return (
              <button
                key={category.id}
                onClick={() => setActiveTab(category.id)}
                className={`flex-shrink-0 px-4 py-3 text-sm font-medium whitespace-nowrap transition-colors ${
                  isActive
                    ? isBadStat
                      ? 'border-b-2 border-red-500 text-red-700 bg-red-50'
                      : isComposite
                      ? 'border-b-2 border-purple-500 text-purple-700 bg-purple-50'
                      : 'border-b-2 border-cyan-500 text-cyan-700 bg-cyan-50'
                    : isBadStat
                    ? 'text-red-600 hover:text-red-700 hover:bg-red-50'
                    : isComposite
                    ? 'text-purple-600 hover:text-purple-700 hover:bg-purple-50'
                    : 'text-gray-600 hover:text-gray-900 hover:bg-gray-50'
                }`}
              >
                {category.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Performers List */}
      <div className="p-4 max-h-[calc(100vh-280px)] overflow-y-auto">
        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <div className="text-center">
              <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-cyan-600 mb-3"></div>
              <p className="text-gray-600">Calculating top performers...</p>
            </div>
          </div>
        ) : activePerformers.length > 0 ? (
          <div className="space-y-2">
            {activePerformers.map((performer, index) => {
              const isFantasyTab = activeCategory?.isComposite;
              
              return (
                <div
                  key={`${performer.playerId}-${index}`}
                  className={`flex items-center p-3 rounded-lg transition-colors ${
                    activeCategory?.isBadStat
                      ? 'bg-red-50 hover:bg-red-100'
                      : isFantasyTab
                      ? 'bg-purple-50 hover:bg-purple-100'
                      : 'bg-gray-50 hover:bg-gray-100'
                  }`}
                >
                  {/* Rank Badge */}
                  <div
                    className={`flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold ${
                      index === 0
                        ? activeCategory?.isBadStat
                          ? 'bg-red-600 text-white'
                          : isFantasyTab
                          ? 'bg-purple-600 text-white'
                          : 'bg-yellow-400 text-gray-900'
                        : index === 1
                        ? activeCategory?.isBadStat
                          ? 'bg-red-500 text-white'
                          : isFantasyTab
                          ? 'bg-purple-500 text-white'
                          : 'bg-gray-300 text-gray-900'
                        : index === 2
                        ? activeCategory?.isBadStat
                          ? 'bg-red-400 text-white'
                          : isFantasyTab
                          ? 'bg-purple-400 text-white'
                          : 'bg-orange-300 text-gray-900'
                        : activeCategory?.isBadStat
                        ? 'bg-red-200 text-red-900'
                        : isFantasyTab
                        ? 'bg-purple-200 text-purple-900'
                        : 'bg-gray-200 text-gray-700'
                    }`}
                  >
                    {index + 1}
                  </div>

                  {/* Player Info */}
                  <div className="ml-3 min-w-0 flex-shrink-0">
                    {onPlayerClick ? (
                      <button
                        onClick={() => onPlayerClick(performer.playerId, performer.playerName)}
                        className="text-left group"
                      >
                        <div className={`font-semibold text-gray-900 transition-colors whitespace-nowrap ${
                          isFantasyTab ? 'group-hover:text-purple-600' : 'group-hover:text-cyan-600'
                        }`}>
                          {performer.playerName}
                        </div>
                        <div className="text-xs text-gray-600">
                          {performer.teamTricode} • {performer.minutes}
                        </div>
                      </button>
                    ) : (
                      <>
                        <div className="font-semibold text-gray-900 whitespace-nowrap">
                          {performer.playerName}
                        </div>
                        <div className="text-xs text-gray-600">
                          {performer.teamTricode} • {performer.minutes}
                        </div>
                      </>
                    )}
                  </div>

                  {/* Full Stat Line - hidden on small screens and in compact mode */}
                  {!compact && (
                    <div className="hidden lg:flex flex-1 items-center justify-center mx-4 gap-3 text-xs text-gray-600">
                      <span className={activeTab === 'pts' ? 'font-bold text-gray-900' : ''}>{performer.pts} PTS</span>
                      <span className={activeTab === 'reb' ? 'font-bold text-gray-900' : ''}>{performer.reb} REB</span>
                      <span className={activeTab === 'ast' ? 'font-bold text-gray-900' : ''}>{performer.ast} AST</span>
                      <span className={activeTab === 'stl' ? 'font-bold text-gray-900' : ''}>{performer.stl} STL</span>
                      <span className={activeTab === 'blk' ? 'font-bold text-gray-900' : ''}>{performer.blk} BLK</span>
                      <span className={activeTab === 'to' ? 'font-bold text-red-700' : ''}>{performer.to} TO</span>
                    </div>
                  )}

                  {/* Stat Value */}
                  <div className="flex-shrink-0 ml-auto text-right">
                    {isFantasyTab ? (
                      // Fantasy value display
                      <>
                        <div className={`text-xl font-bold ${
                          (performer.fantasyValue || 0) >= 0 ? 'text-purple-700' : 'text-gray-500'
                        }`}>
                          {(performer.fantasyValue || 0) >= 0 ? '+' : ''}{(performer.fantasyValue || 0).toFixed(1)}
                        </div>
                        <div className="text-xs text-gray-600 mt-0.5">
                          {performer.pts}/{performer.reb}/{performer.ast}
                        </div>
                      </>
                    ) : (
                      // Regular stat display
                      <>
                        <div
                          className={`text-xl font-bold ${
                            activeCategory?.isBadStat ? 'text-red-700' : 'text-gray-900'
                          }`}
                        >
                          {performer.statValue}
                        </div>
                        {performer.made !== undefined && performer.percentage !== undefined && (
                          <div className="text-xs text-gray-600 mt-0.5">
                            {performer.made}-{performer.statValue} ({(performer.percentage * 100).toFixed(1)}%)
                          </div>
                        )}
                      </>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
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
                d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
              />
            </svg>
            <p className="text-gray-600">No performances recorded</p>
            <p className="text-sm text-gray-500 mt-1">
              {games.length === 0
                ? 'No games available for this date'
                : 'No players with recorded stats'}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

