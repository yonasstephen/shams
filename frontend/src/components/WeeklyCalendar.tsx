/**
 * Weekly calendar component showing 7 days with game counts
 */

import { useState, useEffect } from 'react';
import type { BoxScoreDate } from '../types/api';

interface WeeklyCalendarProps {
  selectedDate: string;
  onDateSelect: (date: string) => void;
  allDates: BoxScoreDate[];
}

export function WeeklyCalendar({ selectedDate, onDateSelect, allDates }: WeeklyCalendarProps) {
  const [weekStart, setWeekStart] = useState<Date>(new Date(selectedDate));

  // Create map of date -> game count for quick lookup
  const dateGameCounts = new Map<string, number>();
  allDates.forEach(d => dateGameCounts.set(d.date, d.game_count));

  // Calculate the start of the week centered on selected date
  useEffect(() => {
    const selected = new Date(selectedDate);
    // Go back 3 days to center the selected date
    const start = new Date(selected);
    start.setDate(start.getDate() - 3);
    setWeekStart(start);
  }, [selectedDate]);

  // Generate 7 days starting from weekStart
  const weekDays: Date[] = [];
  for (let i = 0; i < 7; i++) {
    const day = new Date(weekStart);
    day.setDate(weekStart.getDate() + i);
    weekDays.push(day);
  }

  const formatDate = (date: Date): string => {
    return date.toISOString().split('T')[0];
  };

  const formatDayOfWeek = (date: Date): string => {
    return date.toLocaleDateString('en-US', { weekday: 'short' });
  };

  const formatDayOfMonth = (date: Date): string => {
    return date.getDate().toString();
  };

  const formatMonthYear = (date: Date): string => {
    return date.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
  };

  const goToPreviousWeek = () => {
    const newStart = new Date(weekStart);
    newStart.setDate(newStart.getDate() - 7);
    setWeekStart(newStart);
  };

  const goToNextWeek = () => {
    const newStart = new Date(weekStart);
    newStart.setDate(newStart.getDate() + 7);
    setWeekStart(newStart);
  };

  const isToday = (date: Date): boolean => {
    const today = new Date();
    return formatDate(date) === formatDate(today);
  };

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-3 md:p-4 mb-4 md:mb-6">
      {/* Header with month/year and navigation */}
      <div className="flex items-center justify-between mb-3 md:mb-4">
        <button
          onClick={goToPreviousWeek}
          className="p-1.5 md:p-2 hover:bg-gray-100 rounded-lg transition-colors"
          aria-label="Previous week"
        >
          <svg
            className="w-4 md:w-5 h-4 md:h-5 text-gray-600"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M15 19l-7-7 7-7"
            />
          </svg>
        </button>

        <h2 className="text-base md:text-lg font-semibold text-gray-900">
          {formatMonthYear(weekDays[3])}
        </h2>

        <button
          onClick={goToNextWeek}
          className="p-1.5 md:p-2 hover:bg-gray-100 rounded-lg transition-colors"
          aria-label="Next week"
        >
          <svg
            className="w-4 md:w-5 h-4 md:h-5 text-gray-600"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M9 5l7 7-7 7"
            />
          </svg>
        </button>
      </div>

      {/* Days grid */}
      <div className="grid grid-cols-7 gap-1 md:gap-2">
        {weekDays.map((day) => {
          const dateStr = formatDate(day);
          const gameCount = dateGameCounts.get(dateStr) || 0;
          const isSelected = dateStr === selectedDate;
          const isTodayDate = isToday(day);

          return (
            <button
              key={dateStr}
              onClick={() => onDateSelect(dateStr)}
              className={`
                relative p-2 md:p-3 rounded-lg text-center transition-all min-h-[70px] md:min-h-[90px]
                ${isSelected
                  ? 'bg-neutral-900 text-white shadow-md'
                  : gameCount > 0
                  ? 'bg-gray-50 hover:bg-gray-100 text-gray-900'
                  : 'bg-white hover:bg-gray-50 text-gray-400'
                }
                ${isTodayDate && !isSelected ? 'ring-2 ring-blue-500' : ''}
              `}
            >
              {isTodayDate && (
                <div
                  className={`
                    absolute -top-1.5 md:-top-2 left-1/2 transform -translate-x-1/2
                    px-1.5 md:px-2 py-0.5 rounded-full text-[10px] md:text-xs font-bold
                    ${isSelected
                      ? 'bg-blue-500 text-white'
                      : 'bg-blue-500 text-white'
                    }
                  `}
                >
                  TODAY
                </div>
              )}
              <div className="text-[10px] md:text-xs font-medium mb-0.5 md:mb-1">
                {formatDayOfWeek(day)}
              </div>
              <div className="text-base md:text-lg font-bold mb-0.5 md:mb-1">
                {formatDayOfMonth(day)}
              </div>
              {gameCount > 0 && (
                <div
                  className={`
                    text-[10px] md:text-xs font-medium
                    ${isSelected ? 'text-gray-300' : 'text-gray-600'}
                  `}
                >
                  {gameCount} <span className="hidden md:inline">{gameCount === 1 ? 'game' : 'games'}</span>
                </div>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}

