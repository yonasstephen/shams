// Stat colours from the web app's tables (frontend/src/utils/statColors.ts, which carries the
// defaults of tools/utils/stat_thresholds.py), so a number reads the same in both places.
// The thresholds are per game, so only per-game numbers get coloured.

export type StatTone = "good" | "fair" | "poor" | "dim" | "plain";

export type ColouredStat =
  | "minutes" | "points" | "rebounds" | "assists" | "threes" | "steals" | "blocks"
  | "turnovers" | "fg_pct" | "ft_pct";

/** [fair from, good from] for stats where more is better. */
const RISING: Partial<Record<ColouredStat, [number, number]>> = {
  minutes: [10, 18],
  points: [5, 13],
  rebounds: [5, 9],
  assists: [3, 6],
  threes: [2, 4],
  steals: [2, 3],
  blocks: [2, 3],
};

/** [poor below, fair below] for shooting percentages. */
const SHOOTING: Partial<Record<ColouredStat, [number, number]>> = {
  fg_pct: [0.3, 0.5],
  ft_pct: [0.6, 0.8],
};

export function statTone(stat: ColouredStat, value: number): StatTone {
  if (stat === "turnovers") {
    if (value <= 2) return "good";
    return value <= 4 ? "fair" : "poor";
  }

  const shooting = SHOOTING[stat];
  if (shooting) {
    if (value < shooting[0]) return "poor";
    return value < shooting[1] ? "fair" : "good";
  }

  const rising = RISING[stat];
  if (!rising) return "plain";
  if (value >= rising[1]) return "good";
  return value >= rising[0] ? "fair" : "plain";
}

export function trendTone(delta: number): StatTone {
  if (delta > 0) return "good";
  return delta < 0 ? "poor" : "dim";
}

/** The web app's last-game colouring: a week without playing is a warning, three days a hint. */
export function idleTone(daysSince: number): StatTone {
  if (daysSince > 7) return "poor";
  return daysSince > 3 ? "fair" : "plain";
}

export function toneClass(tone: StatTone): string {
  return tone === "plain" ? "" : `shams-tone-${tone}`;
}
