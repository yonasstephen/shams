/**
 * Reusable stat cell component with color coding
 */

import { memo } from 'react';
import { getStatColor, getColorClass, formatStatValue } from '../utils/statColors';

interface StatCellProps {
  statName: string;
  value: number;
  attempts?: { made: number; attempts: number };
  className?: string;
  aggMode?: 'avg' | 'sum' | 'last';
}

function StatCellComponent({ statName, value, attempts, className = '', aggMode }: StatCellProps) {
  let color = getStatColor(statName, value);
  
  // Override color to gray for percentage stats with zero attempts
  const stat = statName.toUpperCase();
  if ((stat.includes('FG%') || stat === 'FG_PCT' || stat.includes('FT%') || stat === 'FT_PCT') && attempts) {
    if (attempts.attempts === 0) {
      color = 'dim';
    }
  }
  
  const colorClass = getColorClass(color);
  const formatted = formatStatValue(statName, value, attempts, aggMode);

  return (
    <td className={`px-2 py-1.5 text-right text-xs ${colorClass} ${className}`}>
      {formatted}
    </td>
  );
}

// Rankings/waiver tables render hundreds of these; memoize so unrelated parent
// re-renders (e.g. typing in the search box) don't re-render every cell. The
// custom comparator compares `attempts` by value because call sites pass a fresh
// object literal each render, which would otherwise defeat the default shallow check.
export const StatCell = memo(StatCellComponent, (prev, next) => {
  return (
    prev.statName === next.statName &&
    prev.value === next.value &&
    prev.className === next.className &&
    prev.aggMode === next.aggMode &&
    prev.attempts?.made === next.attempts?.made &&
    prev.attempts?.attempts === next.attempts?.attempts
  );
});

