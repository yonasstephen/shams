/**
 * Modal component for displaying player performance insights from play-by-play data
 */

import { useState, useEffect } from 'react';
import { api } from '../services/api';
import type { PlayerInsightsResponse, PlayerInsight, QuarterBreakdown, FoulEvent } from '../types/api';

interface PlayerInsightsModalProps {
  playerId: number;
  playerName: string;
  gameId: string;
  isOpen: boolean;
  onClose: () => void;
}

export function PlayerInsightsModal({ playerId, playerName, gameId, isOpen, onClose }: PlayerInsightsModalProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [insights, setInsights] = useState<PlayerInsightsResponse | null>(null);

  useEffect(() => {
    if (isOpen && playerId && gameId) {
      fetchInsights();
    }
  }, [isOpen, playerId, gameId]);

  const fetchInsights = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getPlayerInsights(gameId, playerId);
      setInsights(data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to fetch player insights. Play-by-play data may not be available for this game.');
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  // Format minutes from float to MM:SS format
  const formatMinutes = (minutes: number): string => {
    const mins = Math.floor(minutes);
    const secs = Math.round((minutes - mins) * 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case 'critical':
        return 'bg-red-100 text-red-800 border-red-200';
      case 'warning':
        return 'bg-amber-100 text-amber-800 border-amber-200';
      default:
        return 'bg-blue-100 text-blue-800 border-blue-200';
    }
  };

  const getSeverityIcon = (severity: string) => {
    switch (severity) {
      case 'critical':
        return (
          <svg className="w-5 h-5 text-red-600" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
          </svg>
        );
      case 'warning':
        return (
          <svg className="w-5 h-5 text-amber-600" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
          </svg>
        );
      default:
        return (
          <svg className="w-5 h-5 text-blue-600" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
          </svg>
        );
    }
  };

  const formatFoulType = (type: string) => {
    return type.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ');
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div 
        className="bg-white rounded-xl shadow-2xl max-w-4xl w-full max-h-[90vh] overflow-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 flex justify-between items-center">
          <div>
            <h2 className="text-xl font-bold text-neutral-900">{insights?.player_name || playerName}</h2>
            <p className="text-sm text-gray-500">Performance Insights</p>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 transition-colors text-2xl font-bold"
          >
            &times;
          </button>
        </div>

        <div className="p-6">
          {/* Loading state */}
          {loading && (
            <div className="flex items-center justify-center py-12">
              <div className="text-center">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-neutral-900 mx-auto mb-4"></div>
                <p className="text-gray-600">Analyzing play-by-play data...</p>
                <p className="text-sm text-gray-400 mt-1">This may take a few seconds</p>
              </div>
            </div>
          )}

          {/* Error state */}
          {error && !loading && (
            <div className="bg-red-50 border border-red-200 rounded-xl p-5">
              <div className="flex items-start">
                <svg className="w-5 h-5 text-red-600 mt-0.5 mr-3 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                </svg>
                <div>
                  <h3 className="text-sm font-medium text-red-800">Unable to load insights</h3>
                  <p className="text-sm text-red-700 mt-1">{error}</p>
                </div>
              </div>
            </div>
          )}

          {/* Insights content */}
          {insights && !loading && !error && (
            <div className="space-y-6">
              {/* Summary */}
              <div className="bg-gray-50 rounded-lg p-4">
                <div className="flex items-center justify-between">
                  <span className="text-gray-600">Total Minutes</span>
                  <span className="text-xl font-bold text-neutral-900 font-mono">{formatMinutes(insights.total_minutes)}</span>
                </div>
              </div>

              {/* Key Insights */}
              {insights.insights.length > 0 && (
                <div className="space-y-3">
                  <h3 className="text-lg font-semibold text-neutral-900">Key Insights</h3>
                  {insights.insights.map((insight: PlayerInsight, idx: number) => (
                    <div 
                      key={idx} 
                      className={`flex items-start gap-3 p-4 rounded-lg border ${getSeverityColor(insight.severity)}`}
                    >
                      {getSeverityIcon(insight.severity)}
                      <div>
                        <p className="font-medium">{insight.message}</p>
                        {insight.details && (
                          <p className="text-sm mt-1 opacity-75">
                            {Object.entries(insight.details).map(([key, value]) => (
                              <span key={key} className="mr-3">
                                {key.replace(/_/g, ' ')}: {Array.isArray(value) ? value.join(', ') : String(value)}
                              </span>
                            ))}
                          </p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {insights.insights.length === 0 && (
                <div className="bg-green-50 border border-green-200 rounded-lg p-4">
                  <div className="flex items-center gap-3">
                    <svg className="w-5 h-5 text-green-600" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                    </svg>
                    <p className="text-green-800 font-medium">No notable issues detected in this game</p>
                  </div>
                </div>
              )}

              {/* Quarter Breakdown */}
              {insights.quarter_breakdown.length > 0 && (
                <div>
                  <h3 className="text-lg font-semibold text-neutral-900 mb-3">Quarter Breakdown</h3>
                  <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-gray-200 text-sm">
                      <thead className="bg-gray-50">
                        <tr>
                          <th className="px-3 py-2 text-left font-semibold text-gray-600">Qtr</th>
                          <th className="px-3 py-2 text-right font-semibold text-gray-600">MIN</th>
                          <th className="px-3 py-2 text-right font-semibold text-gray-600">PTS</th>
                          <th className="px-3 py-2 text-right font-semibold text-gray-600">FG</th>
                          <th className="px-3 py-2 text-right font-semibold text-gray-600">3PT</th>
                          <th className="px-3 py-2 text-right font-semibold text-gray-600">FT</th>
                          <th className="px-3 py-2 text-right font-semibold text-gray-600">REB</th>
                          <th className="px-3 py-2 text-right font-semibold text-gray-600">AST</th>
                          <th className="px-3 py-2 text-right font-semibold text-gray-600">STL</th>
                          <th className="px-3 py-2 text-right font-semibold text-gray-600">BLK</th>
                          <th className="px-3 py-2 text-right font-semibold text-gray-600">TO</th>
                          <th className="px-3 py-2 text-right font-semibold text-gray-600">PF</th>
                        </tr>
                      </thead>
                      <tbody className="bg-white divide-y divide-gray-100">
                        {insights.quarter_breakdown.map((q: QuarterBreakdown) => (
                          <tr key={q.quarter} className="hover:bg-gray-50">
                            <td className="px-3 py-2 font-medium text-neutral-900">{q.quarter_label}</td>
                            <td className="px-3 py-2 text-right text-gray-700 font-mono">{formatMinutes(q.minutes)}</td>
                            <td className="px-3 py-2 text-right text-gray-700 font-semibold">{q.points}</td>
                            <td className="px-3 py-2 text-right text-gray-700">
                              {q.field_goals_made}-{q.field_goals_attempted}
                            </td>
                            <td className="px-3 py-2 text-right text-gray-700">
                              {q.three_pointers_made}-{q.three_pointers_attempted}
                            </td>
                            <td className="px-3 py-2 text-right text-gray-700">
                              {q.free_throws_made}-{q.free_throws_attempted}
                            </td>
                            <td className="px-3 py-2 text-right text-gray-700">{q.rebounds}</td>
                            <td className="px-3 py-2 text-right text-gray-700">{q.assists}</td>
                            <td className="px-3 py-2 text-right text-gray-700">{q.steals}</td>
                            <td className="px-3 py-2 text-right text-gray-700">{q.blocks}</td>
                            <td className="px-3 py-2 text-right text-gray-700">{q.turnovers}</td>
                            <td className={`px-3 py-2 text-right ${q.fouls >= 2 ? 'text-red-600 font-semibold' : 'text-gray-700'}`}>
                              {q.fouls}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Foul Timeline */}
              {insights.foul_timeline.length > 0 && (
                <div>
                  <h3 className="text-lg font-semibold text-neutral-900 mb-3">Foul Timeline</h3>
                  <div className="space-y-2">
                    {insights.foul_timeline.map((foul: FoulEvent, idx: number) => (
                      <div 
                        key={idx} 
                        className={`flex items-center justify-between p-3 rounded-lg ${
                          foul.foul_number >= 4 ? 'bg-red-50 border border-red-200' : 'bg-gray-50'
                        }`}
                      >
                        <div className="flex items-center gap-3">
                          <span className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold ${
                            foul.foul_number >= 5 ? 'bg-red-600 text-white' :
                            foul.foul_number >= 4 ? 'bg-red-500 text-white' :
                            foul.foul_number >= 3 ? 'bg-amber-500 text-white' :
                            'bg-gray-300 text-gray-700'
                          }`}>
                            {foul.foul_number}
                          </span>
                          <div>
                            <p className="font-medium text-neutral-900">{formatFoulType(foul.foul_type)} Foul</p>
                            <p className="text-sm text-gray-500">
                              {formatMinutes(foul.elapsed_minutes)} into game
                            </p>
                          </div>
                        </div>
                        <div className="text-right">
                          <p className="font-mono text-neutral-900">Q{foul.quarter} {foul.time_remaining}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Substitution Timeline - Collapsible */}
              {insights.substitution_timeline.length > 0 && (
                <details className="group">
                  <summary className="cursor-pointer text-lg font-semibold text-neutral-900 mb-3 list-none flex items-center gap-2">
                    <svg className="w-5 h-5 transform group-open:rotate-90 transition-transform" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z" clipRule="evenodd" />
                    </svg>
                    Substitution Timeline ({insights.substitution_timeline.length} events)
                  </summary>
                  <div className="mt-3 space-y-1">
                    {insights.substitution_timeline.map((sub, idx) => (
                      <div 
                        key={idx} 
                        className={`flex items-center justify-between p-2 rounded text-sm ${
                          sub.event_type === 'in' ? 'bg-green-50' : 'bg-gray-100'
                        }`}
                      >
                        <div className="flex items-center gap-2">
                          <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                            sub.event_type === 'in' ? 'bg-green-200 text-green-800' : 'bg-gray-300 text-gray-700'
                          }`}>
                            {sub.event_type === 'in' ? 'IN' : 'OUT'}
                          </span>
                          <span className="text-gray-600 font-mono">{formatMinutes(sub.elapsed_minutes)}</span>
                        </div>
                        <span className="font-mono text-gray-600">Q{sub.quarter} {sub.time_remaining}</span>
                      </div>
                    ))}
                  </div>
                </details>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
