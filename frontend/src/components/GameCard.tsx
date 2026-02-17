/**
 * Game card component for displaying individual game box scores
 */

import { useState } from 'react';
import { BoxScoreTable } from './BoxScoreTable';
import { PlayerInsightsModal } from './PlayerInsightsModal';
import type { GameBoxScore, PlayerBoxScore } from '../types/api';

interface GameCardProps {
  game: GameBoxScore;
  onPlayerClick?: (playerId: number, playerName: string) => void;
}

export function GameCard({ game, onPlayerClick }: GameCardProps) {
  const [expanded, setExpanded] = useState(!game.is_scheduled);  // Auto-expand games with box scores
  const [inspectedPlayer, setInspectedPlayer] = useState<{
    playerId: number;
    playerName: string;
    gameId: string;
  } | null>(null);

  const handleInspectPlayer = (playerId: number, playerName: string, gameId: string) => {
    setInspectedPlayer({ playerId, playerName, gameId });
  };

  // Separate players by team
  const homePlayers: PlayerBoxScore[] = [];
  const awayPlayers: PlayerBoxScore[] = [];

  Object.values(game.box_score || {}).forEach((player) => {
    if (player.TEAM_ID === game.home_team) {
      homePlayers.push(player);
    } else if (player.TEAM_ID === game.away_team) {
      awayPlayers.push(player);
    }
  });

  const homeTeamName = game.home_team_name || game.home_team_tricode || `Team ${game.home_team}`;
  const awayTeamName = game.away_team_name || game.away_team_tricode || `Team ${game.away_team}`;
  
  // Format game time for scheduled games
  const formatGameTime = (isoTime: string | null | undefined): string => {
    if (!isoTime) return '';
    try {
      const date = new Date(isoTime);
      return date.toLocaleTimeString('en-US', { 
        hour: 'numeric', 
        minute: '2-digit',
        timeZoneName: 'short'
      });
    } catch {
      return '';
    }
  };

  return (
    <div className="card bg-white">
      {/* Game header - clickable to expand */}
      <div
        className={`p-3 md:p-4 hover:bg-gray-50 transition-colors ${
          game.is_scheduled ? '' : 'cursor-pointer'
        }`}
        onClick={() => !game.is_scheduled && setExpanded(!expanded)}
      >
        {/* Mobile layout: stacked */}
        <div className="md:hidden space-y-2">
          {/* Teams and scores */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="font-semibold text-gray-900 text-sm">
                {awayTeamName}
              </span>
              {!game.is_scheduled && (
                <span className="text-lg font-bold text-gray-900">
                  {game.away_score ?? '-'}
                </span>
              )}
            </div>
            {!game.is_scheduled && (
              <svg
                className={`w-5 h-5 text-gray-400 transition-transform ${
                  expanded ? 'rotate-180' : ''
                }`}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M19 9l-7 7-7-7"
                />
              </svg>
            )}
          </div>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-gray-400 text-xs font-medium">@</span>
              <span className="font-semibold text-gray-900 text-sm">
                {homeTeamName}
              </span>
              {!game.is_scheduled && (
                <span className="text-lg font-bold text-gray-900">
                  {game.home_score ?? '-'}
                </span>
              )}
            </div>
          </div>
          
          {/* Scheduled game indicator */}
          {game.is_scheduled && game.game_time && (
            <div className="flex items-center gap-2">
              {game.postponed_status === 'Y' ? (
                <span className="px-2 py-1 text-xs font-medium bg-red-100 text-red-800 rounded">
                  PPD
                </span>
              ) : (
                <span className="px-2 py-1 text-xs font-medium bg-blue-100 text-blue-800 rounded">
                  Scheduled
                </span>
              )}
              <span className="text-xs text-gray-600">
                {formatGameTime(game.game_time)}
              </span>
            </div>
          )}
        </div>

        {/* Desktop layout: side-by-side */}
        <div className="hidden md:flex items-center justify-between">
          <div className="flex items-center gap-6 flex-1">
            {/* Away team */}
            <div className="flex items-center gap-3 min-w-[140px]">
              <span className="font-semibold text-gray-900 text-lg">
                {awayTeamName}
              </span>
              {!game.is_scheduled && (
                <span className="text-2xl font-bold text-gray-900">
                  {game.away_score ?? '-'}
                </span>
              )}
            </div>

            <span className="text-gray-400 font-medium">@</span>

            {/* Home team */}
            <div className="flex items-center gap-3 min-w-[140px]">
              <span className="font-semibold text-gray-900 text-lg">
                {homeTeamName}
              </span>
              {!game.is_scheduled && (
                <span className="text-2xl font-bold text-gray-900">
                  {game.home_score ?? '-'}
                </span>
              )}
            </div>
            
            {/* Scheduled game indicator */}
            {game.is_scheduled && game.game_time && (
              <div className="flex items-center gap-2 ml-4">
                {game.postponed_status === 'Y' ? (
                  <span className="px-2 py-1 text-xs font-medium bg-red-100 text-red-800 rounded">
                    PPD
                  </span>
                ) : (
                  <span className="px-2 py-1 text-xs font-medium bg-blue-100 text-blue-800 rounded">
                    Scheduled
                  </span>
                )}
                <span className="text-sm text-gray-600">
                  {formatGameTime(game.game_time)}
                </span>
              </div>
            )}
          </div>

          {/* Expand/collapse indicator - only for games with box scores */}
          {!game.is_scheduled && (
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-500">
                {expanded ? 'Hide' : 'Show'} Box Score
              </span>
              <svg
                className={`w-5 h-5 text-gray-400 transition-transform ${
                  expanded ? 'rotate-180' : ''
                }`}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M19 9l-7 7-7-7"
                />
              </svg>
            </div>
          )}
        </div>
      </div>

      {/* Expanded box score tables - only for games with actual box scores */}
      {expanded && !game.is_scheduled && (
        <div className="border-t border-gray-200">
          {/* Away team box score */}
          <div className="p-3 md:p-4 border-b border-gray-200">
            <div className="flex items-center justify-between mb-2 md:mb-3">
              <h3 className="text-sm md:text-base font-bold text-gray-900">
                {awayTeamName}
              </h3>
              <span className="text-xl md:text-2xl font-bold text-gray-900">
                {game.away_score ?? '-'}
              </span>
            </div>
            <BoxScoreTable 
              players={awayPlayers} 
              teamTricode={awayTeamName} 
              gameId={game.game_id}
              onPlayerClick={onPlayerClick}
              onInspectPlayer={handleInspectPlayer}
            />
          </div>

          {/* Home team box score */}
          <div className="p-3 md:p-4">
            <div className="flex items-center justify-between mb-2 md:mb-3">
              <h3 className="text-sm md:text-base font-bold text-gray-900">
                {homeTeamName}
              </h3>
              <span className="text-xl md:text-2xl font-bold text-gray-900">
                {game.home_score ?? '-'}
              </span>
            </div>
            <BoxScoreTable 
              players={homePlayers} 
              teamTricode={homeTeamName}
              gameId={game.game_id}
              onPlayerClick={onPlayerClick}
              onInspectPlayer={handleInspectPlayer}
            />
          </div>
        </div>
      )}

      {/* Player Insights Modal */}
      {inspectedPlayer && (
        <PlayerInsightsModal
          playerId={inspectedPlayer.playerId}
          playerName={inspectedPlayer.playerName}
          gameId={inspectedPlayer.gameId}
          isOpen={!!inspectedPlayer}
          onClose={() => setInspectedPlayer(null)}
        />
      )}
    </div>
  );
}

