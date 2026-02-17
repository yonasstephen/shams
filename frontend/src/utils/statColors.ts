/**
 * Stat color utilities matching CLI thresholds
 */

// Thresholds from tools/utils/stat_thresholds.py
const THRESHOLDS = {
  PTS: { yellow: 5, green: 13 },
  REB: { yellow: 5, green: 9 },
  AST: { yellow: 3, green: 6 },
  '3PM': { yellow: 2, green: 4 },
  STL: { yellow: 2, green: 3 },
  BLK: { yellow: 2, green: 3 },
  TO: { green: 2, yellow: 4 }, // Inverted (lower is better)
  'FG%': { red: 0.30, yellow: 0.50 },
  'FT%': { red: 0.60, yellow: 0.80 },
  'USG%': { yellow: 0.15, green: 0.25 },
  MIN: { yellow: 10, green: 18 },
  '+/-': { yellow: 5, green: 10, red: -5, darkRed: -10 },
};

export type StatColor = 'green' | 'yellow' | 'red' | 'dim' | 'default';

export function getStatColor(statName: string, value: number): StatColor {
  const stat = statName.toUpperCase();

  // Percentages
  if (stat.includes('FG%') || stat === 'FG_PCT') {
    const thresh = THRESHOLDS['FG%'];
    if (value < thresh.red) return 'red';
    if (value < thresh.yellow) return 'yellow';
    return 'green';
  }

  if (stat.includes('FT%') || stat === 'FT_PCT') {
    const thresh = THRESHOLDS['FT%'];
    if (value < thresh.red) return 'red';
    if (value < thresh.yellow) return 'yellow';
    return 'green';
  }

  if (stat.includes('USG') || stat === 'USAGE_PCT') {
    const thresh = THRESHOLDS['USG%'];
    if (value >= thresh.green) return 'green';
    if (value >= thresh.yellow) return 'yellow';
    return 'default';
  }

  // Turnovers (inverted)
  if (stat === 'TO' || stat === 'TURNOVERS') {
    const thresh = THRESHOLDS.TO;
    if (value <= thresh.green) return 'green';
    if (value <= thresh.yellow) return 'yellow';
    return 'red';
  }

  // Counting stats
  if (stat === 'PTS' || stat === 'POINTS') {
    const thresh = THRESHOLDS.PTS;
    if (value >= thresh.green) return 'green';
    if (value >= thresh.yellow) return 'yellow';
    return 'default';
  }

  if (stat === 'REB' || stat === 'REBOUNDS') {
    const thresh = THRESHOLDS.REB;
    if (value >= thresh.green) return 'green';
    if (value >= thresh.yellow) return 'yellow';
    return 'default';
  }

  if (stat === 'AST' || stat === 'ASSISTS') {
    const thresh = THRESHOLDS.AST;
    if (value >= thresh.green) return 'green';
    if (value >= thresh.yellow) return 'yellow';
    return 'default';
  }

  if (stat === '3PM' || stat === 'THREES' || stat === '3PTM') {
    const thresh = THRESHOLDS['3PM'];
    if (value >= thresh.green) return 'green';
    if (value >= thresh.yellow) return 'yellow';
    return 'default';
  }

  if (stat === 'STL' || stat === 'STEALS') {
    const thresh = THRESHOLDS.STL;
    if (value >= thresh.green) return 'green';
    if (value >= thresh.yellow) return 'yellow';
    return 'default';
  }

  if (stat === 'BLK' || stat === 'BLOCKS') {
    const thresh = THRESHOLDS.BLK;
    if (value >= thresh.green) return 'green';
    if (value >= thresh.yellow) return 'yellow';
    return 'default';
  }

  if (stat === 'MIN' || stat === 'MINUTE' || stat === 'MINUTES') {
    const thresh = THRESHOLDS.MIN;
    if (value >= thresh.green) return 'green';
    if (value >= thresh.yellow) return 'yellow';
    return 'default';
  }

  // Plus/minus
  if (stat === 'PLUS_MINUS' || stat === '+/-') {
    const thresh = THRESHOLDS['+/-'];
    if (value >= thresh.green) return 'green';
    if (value >= thresh.yellow) return 'yellow';
    if (value <= thresh.darkRed) return 'red';
    if (value <= thresh.red) return 'yellow';
    return 'default';
  }

  return 'default';
}

export function getColorClass(color: StatColor): string {
  const colorMap: Record<StatColor, string> = {
    green: 'text-stat-green font-semibold',
    yellow: 'text-stat-yellow font-semibold',
    red: 'text-stat-red font-semibold',
    dim: 'text-stat-dim',
    default: 'text-gray-900',
  };
  return colorMap[color];
}

export function getBgColorClass(color: StatColor): string {
  const colorMap: Record<StatColor, string> = {
    green: 'bg-green-100 text-green-900 font-semibold',
    yellow: 'bg-yellow-100 text-yellow-900 font-semibold',
    red: 'bg-red-100 text-red-900 font-semibold',
    dim: 'bg-gray-100 text-gray-600',
    default: 'bg-white text-gray-900',
  };
  return colorMap[color];
}

export function getTrendColor(trend: number): StatColor {
  if (trend > 0) return 'green';
  if (trend < 0) return 'red';
  return 'dim';
}

export function formatStatValue(
  statName: string, 
  value: number, 
  includeAttempts?: { made: number; attempts: number },
  aggMode?: 'avg' | 'sum' | 'last'
): string {
  const stat = statName.toUpperCase();

  // Percentages - always show decimal
  if (stat.includes('%') || stat.includes('PCT')) {
    const formatted = `${(value * 100).toFixed(1)}%`;
    if (includeAttempts) {
      return `${formatted} (${includeAttempts.made.toFixed(0)}/${includeAttempts.attempts.toFixed(0)})`;
    }
    return formatted;
  }

  // Regular stats - show decimal for avg, integer for sum/last
  if (aggMode === 'avg') {
    return value.toFixed(1);
  } else {
    return value.toFixed(0);
  }
}

// Margin thresholds for gradated colors (weekly totals)
const MARGIN_THRESHOLDS = {
  PTS: { low: 1, mid: 20, high: 51 },
  REB: { low: 1, mid: 6, high: 20 },
  AST: { low: 1, mid: 6, high: 15 },
  '3PM': { low: 1, mid: 4, high: 15 },
  STL: { low: 1, mid: 3, high: 6 },
  BLK: { low: 1, mid: 3, high: 6 },
  TO: { low: 1, mid: 3, high: 10 },
  'FG%': { low: 0.005, mid: 0.02, high: 0.10 },
  'FT%': { low: 0.005, mid: 0.02, high: 0.10 },
};

export type MarginIntensity = 'light' | 'medium' | 'dark' | 'neutral';

/**
 * Get background color class based on margin size and stat type
 * Returns gradated colors: light/medium/dark green for positive margins,
 * light/medium/dark red for negative margins
 */
export function getMarginColorClass(statName: string, margin: number): string {
  const absMargin = Math.abs(margin);
  
  // Exact tie
  if (margin === 0) {
    return 'bg-gray-100 text-gray-700';
  }

  // Determine thresholds based on stat name
  let thresholds = { low: 1, mid: 5, high: 10 };
  
  const stat = statName.toUpperCase();
  if (stat.includes('PTS') || stat.includes('POINTS')) {
    thresholds = MARGIN_THRESHOLDS.PTS;
  } else if (stat.includes('REB') || stat.includes('REBOUNDS')) {
    thresholds = MARGIN_THRESHOLDS.REB;
  } else if (stat.includes('AST') || stat.includes('ASSISTS')) {
    thresholds = MARGIN_THRESHOLDS.AST;
  } else if (stat.includes('3PM') || stat.includes('3PTM') || stat.includes('THREES')) {
    thresholds = MARGIN_THRESHOLDS['3PM'];
  } else if (stat.includes('STL') || stat.includes('STEALS')) {
    thresholds = MARGIN_THRESHOLDS.STL;
  } else if (stat.includes('BLK') || stat.includes('BLOCKS')) {
    thresholds = MARGIN_THRESHOLDS.BLK;
  } else if (stat.includes('TO') || stat.includes('TURNOVERS')) {
    thresholds = MARGIN_THRESHOLDS.TO;
  } else if (stat.includes('FG%') || stat.includes('FG_PCT')) {
    thresholds = MARGIN_THRESHOLDS['FG%'];
  } else if (stat.includes('FT%') || stat.includes('FT_PCT')) {
    thresholds = MARGIN_THRESHOLDS['FT%'];
  }

  // Determine intensity based on absolute margin
  let intensity: MarginIntensity;
  if (absMargin >= thresholds.high) {
    intensity = 'dark';
  } else if (absMargin >= thresholds.mid) {
    intensity = 'medium';
  } else if (absMargin >= thresholds.low) {
    intensity = 'light';
  } else {
    intensity = 'neutral';
  }

  // Return appropriate color class
  const isPositive = margin > 0;
  
  if (intensity === 'neutral') {
    return 'bg-gray-100 text-gray-700';
  }
  
  if (isPositive) {
    if (intensity === 'dark') return 'bg-green-300 text-green-900 font-semibold';
    if (intensity === 'medium') return 'bg-green-200 text-green-900 font-semibold';
    return 'bg-green-100 text-green-900 font-semibold'; // light
  } else {
    if (intensity === 'dark') return 'bg-red-300 text-red-900 font-semibold';
    if (intensity === 'medium') return 'bg-red-200 text-red-900 font-semibold';
    return 'bg-red-100 text-red-900 font-semibold'; // light
  }
}

