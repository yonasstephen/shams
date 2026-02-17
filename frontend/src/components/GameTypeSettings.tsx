/**
 * Game Type Settings Component
 * Allows users to configure which NBA game types count towards Yahoo Fantasy stats
 */

import { useState, useEffect } from 'react';
import { api } from '../services/api';
import type { GameTypeSettingsResponse } from '../types/api';

interface GameTypeSettingsProps {
  leagueKey?: string | null;
}

export function GameTypeSettings({ leagueKey: _leagueKey }: GameTypeSettingsProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);
  
  const [settingsData, setSettingsData] = useState<GameTypeSettingsResponse | null>(null);
  const [localSettings, setLocalSettings] = useState<Record<string, boolean>>({});
  const [hasChanges, setHasChanges] = useState(false);

  // Fetch settings on mount
  useEffect(() => {
    fetchSettings();
  }, []);

  // Check for changes when local settings update
  useEffect(() => {
    if (settingsData) {
      const changed = Object.keys(localSettings).some(
        key => localSettings[key] !== settingsData.settings[key]
      );
      setHasChanges(changed);
    }
  }, [localSettings, settingsData]);

  const fetchSettings = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await api.getGameTypeSettings();
      setSettingsData(data);
      setLocalSettings({ ...data.settings });
    } catch (err) {
      setError('Failed to load game type settings');
      console.error('Failed to fetch game type settings:', err);
    } finally {
      setIsLoading(false);
    }
  };

  const handleToggle = (key: string) => {
    setLocalSettings(prev => ({
      ...prev,
      [key]: !prev[key],
    }));
    setSaveSuccess(false);
  };

  const handleSave = async () => {
    setIsSaving(true);
    setError(null);
    setSaveSuccess(false);
    try {
      const data = await api.updateGameTypeSettings(localSettings);
      setSettingsData(data);
      setLocalSettings({ ...data.settings });
      setHasChanges(false);
      setSaveSuccess(true);
      // Clear success message after 3 seconds
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (err) {
      setError('Failed to save settings');
      console.error('Failed to save game type settings:', err);
    } finally {
      setIsSaving(false);
    }
  };

  const handleReset = () => {
    if (settingsData) {
      setLocalSettings({ ...settingsData.defaults });
      setSaveSuccess(false);
    }
  };

  const handleRevert = () => {
    if (settingsData) {
      setLocalSettings({ ...settingsData.settings });
      setSaveSuccess(false);
    }
  };

  // Render a toggle switch
  const renderToggle = (key: string, label: string, description: string) => {
    const isEnabled = localSettings[key] ?? false;
    const isDefault = settingsData?.defaults[key] ?? false;
    const hasChanged = settingsData && localSettings[key] !== settingsData.settings[key];
    
    return (
      <div 
        key={key}
        className={`flex items-center justify-between py-3 px-4 rounded-lg transition-colors ${
          hasChanged ? 'bg-amber-50 border border-amber-200' : 'hover:bg-gray-50'
        }`}
      >
        <div className="flex-1 pr-4">
          <div className="flex items-center gap-2">
            <span className="font-medium text-neutral-900">{label}</span>
            {isDefault && (
              <span className="text-xs text-green-600 bg-green-50 px-1.5 py-0.5 rounded">
                default: ON
              </span>
            )}
            {!isDefault && (
              <span className="text-xs text-gray-500 bg-gray-100 px-1.5 py-0.5 rounded">
                default: OFF
              </span>
            )}
          </div>
          <p className="text-sm text-gray-600 mt-0.5">{description}</p>
        </div>
        <button
          onClick={() => handleToggle(key)}
          className={`relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-neutral-900 focus:ring-offset-2 ${
            isEnabled ? 'bg-green-500' : 'bg-gray-300'
          }`}
          role="switch"
          aria-checked={isEnabled}
        >
          <span
            className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
              isEnabled ? 'translate-x-5' : 'translate-x-0'
            }`}
          />
        </button>
      </div>
    );
  };

  // Category display names
  const categoryLabels: Record<string, string> = {
    'Regular Season': '🏀 Regular Season',
    'NBA Cup': '🏆 NBA Cup (In-Season Tournament)',
    'Playoffs': '🏅 Playoffs',
    'Other': '📅 Other Events',
  };

  return (
    <div className="card p-6 mt-6">
      {/* Header */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between text-left"
      >
        <div>
          <h2 className="text-xl font-bold text-gray-900">Game Type Settings</h2>
          <p className="text-sm text-gray-600 mt-1">
            Configure which NBA game types count towards fantasy stats
          </p>
        </div>
        <svg
          className={`w-5 h-5 text-gray-500 transform transition-transform ${
            isExpanded ? 'rotate-180' : ''
          }`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* Expanded Content */}
      {isExpanded && (
        <div className="mt-6 border-t border-gray-200 pt-6">
          {isLoading ? (
            <div className="py-8 text-center">
              <div className="animate-pulse space-y-3">
                <div className="h-10 bg-gray-200 rounded-xl"></div>
                <div className="h-10 bg-gray-200 rounded-xl"></div>
                <div className="h-10 bg-gray-200 rounded-xl"></div>
              </div>
              <p className="mt-4 text-gray-500">Loading settings...</p>
            </div>
          ) : error && !settingsData ? (
            <div className="py-8 text-center">
              <div className="bg-red-50 border border-red-200 rounded-xl p-5 mb-4">
                <p className="text-red-700 font-semibold">Failed to load settings</p>
                <p className="text-red-600 text-sm mt-1.5">{error}</p>
              </div>
              <button
                onClick={fetchSettings}
                className="px-6 py-2.5 bg-neutral-900 text-white rounded-xl hover:bg-neutral-800 transition-colors font-medium"
              >
                Retry
              </button>
            </div>
          ) : settingsData ? (
            <>
              {/* Info Banner */}
              <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 mb-6">
                <div className="flex gap-3">
                  <svg className="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
                  </svg>
                  <div className="text-sm text-blue-800">
                    <p className="font-medium">Changes require a schedule refresh</p>
                    <p className="mt-1 text-blue-700">
                      After saving, run "Refresh NBA Schedule" in the Data Management section above to apply the new filters.
                    </p>
                  </div>
                </div>
              </div>

              {/* Settings by Category */}
              <div className="space-y-6">
                {Object.entries(settingsData.categories).map(([category, keys]) => (
                  <div key={category}>
                    <h3 className="text-lg font-semibold text-neutral-900 mb-3">
                      {categoryLabels[category] || category}
                    </h3>
                    <div className="space-y-1 border border-gray-200 rounded-xl overflow-hidden">
                      {keys.map(key => 
                        renderToggle(
                          key,
                          formatSettingLabel(key),
                          settingsData.descriptions[key] || ''
                        )
                      )}
                    </div>
                  </div>
                ))}
              </div>

              {/* Action Buttons */}
              <div className="mt-6 pt-6 border-t border-gray-200 flex flex-wrap items-center gap-3">
                <button
                  onClick={handleSave}
                  disabled={!hasChanges || isSaving}
                  className={`px-5 py-2.5 rounded-xl font-medium transition-colors ${
                    hasChanges && !isSaving
                      ? 'bg-neutral-900 text-white hover:bg-neutral-800'
                      : 'bg-gray-200 text-gray-500 cursor-not-allowed'
                  }`}
                >
                  {isSaving ? 'Saving...' : 'Save Changes'}
                </button>
                
                {hasChanges && (
                  <button
                    onClick={handleRevert}
                    className="px-5 py-2.5 rounded-xl font-medium text-gray-700 hover:bg-gray-100 transition-colors"
                  >
                    Revert Changes
                  </button>
                )}
                
                <button
                  onClick={handleReset}
                  className="px-5 py-2.5 rounded-xl font-medium text-gray-600 hover:bg-gray-100 transition-colors"
                >
                  Reset to Defaults
                </button>

                {/* Success/Error Messages */}
                {saveSuccess && (
                  <span className="text-green-600 font-medium flex items-center gap-1.5">
                    <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                    </svg>
                    Settings saved
                  </span>
                )}
                
                {error && settingsData && (
                  <span className="text-red-600 font-medium">{error}</span>
                )}
              </div>
            </>
          ) : null}
        </div>
      )}
    </div>
  );
}

/**
 * Format setting key to human-readable label
 */
function formatSettingLabel(key: string): string {
  const labels: Record<string, string> = {
    regular_season: 'Regular Season',
    nba_cup_group_stage: 'NBA Cup Group Stage',
    nba_cup_knockout: 'NBA Cup Knockout Rounds',
    nba_cup_final: 'NBA Cup Final',
    preseason: 'Preseason',
    all_star: 'All-Star Events',
    play_in: 'Play-In Tournament',
    playoffs_first_round: 'Playoffs First Round',
    playoffs_conf_semis: 'Conference Semifinals',
    playoffs_conf_finals: 'Conference Finals',
    nba_finals: 'NBA Finals',
    global_games: 'Global/International Games',
  };
  
  return labels[key] || key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

