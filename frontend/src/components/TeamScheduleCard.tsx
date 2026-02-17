/**
 * Team Schedule Card Component
 * 
 * Displays a compact table showing all 30 NBA teams with their game schedules
 * for a single fantasy week.
 */

import { useState, memo } from 'react';
import type { TeamScheduleInfo } from '../types/api';

interface TeamScheduleCardProps {
  teams: TeamScheduleInfo[];
  weekNumber: number;
  weekType: 'current' | 'next';
  loading?: boolean;
  onCollapse?: () => void;
}

type SortField = 'team' | 'games';
type SortDirection = 'asc' | 'desc';

export const TeamScheduleCard = memo(function TeamScheduleCard({ teams, weekNumber, weekType, loading, onCollapse }: TeamScheduleCardProps) {
  const [sortField, setSortField] = useState<SortField>('games');
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc');

  // Sort teams based on current sort field and direction
  const sortedTeams = [...teams].sort((a, b) => {
    let comparison = 0;

    switch (sortField) {
      case 'team':
        comparison = a.team_abbr.localeCompare(b.team_abbr);
        break;
      case 'games':
        if (weekType === 'current') {
          // Primary sort: remaining games, secondary sort: total games
          comparison = a.current_week_games - b.current_week_games;
          if (comparison === 0) {
            comparison = a.current_week_total - b.current_week_total;
          }
        } else {
          comparison = a.next_week_games - b.next_week_games;
        }
        break;
    }

    return sortDirection === 'asc' ? comparison : -comparison;
  });

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      // Toggle direction if clicking the same field
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      // New field, default to descending for numeric fields, ascending for team name
      setSortField(field);
      setSortDirection(field === 'team' ? 'asc' : 'desc');
    }
  };

  const SortIcon = ({ field }: { field: SortField }) => {
    if (sortField !== field) {
      return <span className="text-gray-400 ml-1">↕</span>;
    }
    return <span className="text-neutral-900 ml-1">{sortDirection === 'asc' ? '↑' : '↓'}</span>;
  };

  // Get dates for the specified week
  const weekDates = weekType === 'current' 
    ? teams[0]?.current_week_dates || []
    : teams[0]?.next_week_dates || [];

  // Format date to show day of week
  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    const dayOfWeek = date.toLocaleDateString('en-US', { weekday: 'short' });
    const dayOfMonth = date.getDate();
    return `${dayOfWeek} ${dayOfMonth}`;
  };

  if (loading) {
    return (
      <div className="card p-6">
        <div className="flex items-center justify-between mb-4">
          <div className="h-6 bg-gray-200 rounded w-40 animate-pulse"></div>
          {onCollapse && weekType === 'current' && (
            <button
              onClick={onCollapse}
              className="text-gray-400 hover:text-gray-600 transition-colors p-1"
              title="Collapse schedules"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          )}
        </div>
        <div className="flex items-center justify-center py-12">
          <div className="flex flex-col items-center">
            <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-neutral-900"></div>
            <p className="mt-3 text-sm text-gray-600">Loading team schedules...</p>
          </div>
        </div>
      </div>
    );
  }

  if (teams.length === 0) {
    return (
      <div className="card p-6">
        <h2 className="text-lg font-bold text-neutral-900 mb-4">Week {weekNumber} Schedule</h2>
        <p className="text-gray-600 text-center py-6">No team schedule data available.</p>
      </div>
    );
  }

  return (
    <div className="card p-6">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-bold text-neutral-900">Week {weekNumber} Schedule</h2>
        {onCollapse && weekType === 'current' && (
          <button
            onClick={onCollapse}
            className="text-gray-400 hover:text-gray-600 transition-colors p-1"
            title="Collapse schedules"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        )}
      </div>
      
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200 text-xs">
          <thead className="bg-neutral-50 sticky top-0 z-10">
            <tr>
              <th 
                className="px-2 py-2 text-left font-semibold text-gray-600 uppercase tracking-wider cursor-pointer hover:bg-neutral-100 transition-colors select-none"
                onClick={() => handleSort('team')}
              >
                <div className="flex items-center">
                  Team
                  <SortIcon field="team" />
                </div>
              </th>
              <th 
                className="px-2 py-2 text-center font-semibold text-gray-600 uppercase tracking-wider cursor-pointer hover:bg-neutral-100 transition-colors select-none"
                onClick={() => handleSort('games')}
              >
                <div className="flex items-center justify-center">
                  Games
                  <SortIcon field="games" />
                </div>
              </th>
              {/* Week dates */}
              {weekDates.map((day) => (
                <th 
                  key={`${weekType}-${day.date}`}
                  className={`px-1 py-2 text-center font-semibold text-gray-600 uppercase tracking-wider ${
                    day.is_past ? 'opacity-50' : ''
                  }`}
                  title={day.date}
                >
                  <div className="text-[10px]">{formatDate(day.date)}</div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-100">
            {sortedTeams.map((team) => {
              const gamesCount = weekType === 'current' ? team.current_week_total : team.next_week_games;
              const gamesRemaining = weekType === 'current' ? team.current_week_games : team.next_week_games;
              const dates = weekType === 'current' ? team.current_week_dates : team.next_week_dates;
              
              return (
                <tr key={team.team_id} className="hover:bg-neutral-50 transition-colors">
                  <td className="px-2 py-1.5 whitespace-nowrap font-medium text-neutral-900">
                    {team.team_abbr}
                  </td>
                  <td className={`px-2 py-1.5 text-center ${
                    gamesRemaining === 0 ? 'text-gray-400' :
                    gamesRemaining >= 4 ? 'text-green-600' :
                    gamesRemaining > 2 ? 'text-yellow-600' : 'text-red-600'
                  }`}>
                    {weekType === 'current' ? `${gamesRemaining}/${gamesCount}` : gamesCount}
                  </td>
                  {/* Week checkmarks */}
                  {dates.map((day, idx) => (
                    <td 
                      key={`${weekType}-${team.team_id}-${idx}`}
                      className={`px-1 py-1.5 text-center ${
                        day.is_past ? 'opacity-40' : ''
                      }`}
                    >
                      {day.is_playing ? (
                        <span className="text-green-600">✓</span>
                      ) : (
                        <span className="text-gray-300">-</span>
                      )}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
});

