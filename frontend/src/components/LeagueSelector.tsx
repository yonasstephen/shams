/**
 * League selector dropdown component
 */

import { useLeague } from '../context/LeagueContext';
import { Dropdown } from './Dropdown';
import type { LeagueInfo } from '../types/api';

export function LeagueSelector() {
  const { leagues, defaultLeagueKey, isLoading, error, setDefaultLeague } = useLeague();

  const handleLeagueChange = async (leagueKey: string | number) => {
    if (leagueKey) {
      try {
        await setDefaultLeague(String(leagueKey));
      } catch (error) {
        console.error('Failed to set league:', error);
      }
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center">
        <div className="animate-pulse bg-gray-200 h-10 w-48 rounded-xl"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center gap-2">
        <div className="text-sm text-red-600" title={error}>
          Failed to load leagues
        </div>
      </div>
    );
  }

  if (leagues.length === 0) {
    return (
      <div className="flex items-center gap-2">
        <div className="text-sm text-yellow-600">
          No leagues found
        </div>
      </div>
    );
  }

  const currentLeague = leagues.find((l: LeagueInfo) => l.league_key === defaultLeagueKey);

  const dropdownOptions = [
    ...(!defaultLeagueKey ? [{ value: '', label: 'Select League...' }] : []),
    ...leagues.map((league: LeagueInfo) => ({
      value: league.league_key,
      label: league.name,
    })),
  ];

  return (
    <div className="flex items-center gap-2">
      <label htmlFor="league-selector" className="sr-only">
        Select League
      </label>
      <Dropdown
        id="league-selector"
        value={defaultLeagueKey || ''}
        onChange={handleLeagueChange}
        options={dropdownOptions}
        title={currentLeague ? `League Key: ${currentLeague.league_key}` : 'Select a league'}
        className="block w-full"
      />
    </div>
  );
}

