/**
 * Reusable stat cell component with color coding
 */

import { getStatColor, getColorClass, formatStatValue } from '../utils/statColors';

interface StatCellProps {
  statName: string;
  value: number;
  attempts?: { made: number; attempts: number };
  className?: string;
  aggMode?: 'avg' | 'sum' | 'last';
}

export function StatCell({ statName, value, attempts, className = '', aggMode }: StatCellProps) {
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

