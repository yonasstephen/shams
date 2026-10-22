// Yahoo stat names -> feed field names. Mirrors _build_stat_name_to_cache_mapping in
// tools/matchup/matchup_projection.py; the same precedent as frontend/src/utils/statColors.ts
// mirroring the Python thresholds.

import type { StatLine } from "../feed/types";

export type StatField = keyof Pick<
  StatLine,
  | "fgm" | "fga" | "fg_pct" | "ftm" | "fta" | "ft_pct"
  | "threes" | "points" | "rebounds" | "assists" | "steals" | "blocks" | "turnovers"
>;

const NAME_TO_FIELD: Record<string, StatField> = {
  "FG%": "fg_pct",
  "FT%": "ft_pct",
  "FGM": "fgm",
  "FGA": "fga",
  "FTM": "ftm",
  "FTA": "fta",
  "3PTM": "threes",
  "3PM": "threes",
  "3-Point Baskets Made": "threes",
  "PTS": "points",
  "Points": "points",
  "REB": "rebounds",
  "Rebounds": "rebounds",
  "AST": "assists",
  "Assists": "assists",
  "ST": "steals",
  "STL": "steals",
  "Steals": "steals",
  "BLK": "blocks",
  "Blocks": "blocks",
  "TO": "turnovers",
  "Turnovers": "turnovers",
};

export function fieldForStatName(name: string): StatField | null {
  return NAME_TO_FIELD[name] ?? null;
}

export function isPercentageStat(name: string): boolean {
  return name.includes("%");
}
