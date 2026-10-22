// Category valuation, ported from tools/draft/value_model.py.
//
// Each player is scored per category as a z-score against a reference pool, so a block and
// a point become comparable. Two rules carried over from the Python:
//   * FG% and FT% score *makes above baseline* — the extra makes a player produces over a
//     league-average shooter on the same attempts — so volume counts. Raw percentage would
//     rate a 60% shooter on two attempts above a 50% shooter on twenty;
//   * categories where less is better (sort_order "0", turnovers) have their z inverted, so
//     positive always means "helps you".
//
// The parity fixture in test/fixtures/valuation.json pins this to the Python.

import type { StatLine } from "../feed/types";
import type { StatCategory } from "../yahoo/types";
import { fieldForStatName, type StatField } from "./statMap";

/** Below this many attempts a percentage contribution is noise. */
const MIN_ATTEMPTS = 1e-6;

const RATIO_FIELDS: Partial<Record<StatField, [StatField, StatField]>> = {
  fg_pct: ["fgm", "fga"],
  ft_pct: ["ftm", "fta"],
};

export interface ValuedCategory {
  statId: string;
  displayName: string;
  field: StatField;
  higherIsBetter: boolean;
}

export interface ValuationContext {
  categories: ValuedCategory[];
  /** Per stat id: mean and standard deviation of the scored quantity across the pool. */
  means: Record<string, number>;
  stddevs: Record<string, number>;
  /** League-average percentage per ratio category: total makes over total attempts. */
  ratioBaselines: Record<string, number>;
  poolSize: number;
}

/** Per stat id, how much a player helps (+) or hurts (−) that category, in pool deviations. */
export type CategoryZ = Record<string, number>;

/** The league's scoring categories that a stat line can answer for. */
export function scoringCategories(categories: StatCategory[]): ValuedCategory[] {
  const scored: ValuedCategory[] = [];
  for (const category of categories) {
    if (category.isDisplayOnly) continue;
    const field = fieldForStatName(category.displayName) ?? fieldForStatName(category.name);
    if (!field) continue;
    scored.push({
      statId: category.statId,
      displayName: category.displayName,
      field,
      higherIsBetter: category.sortOrder !== "0",
    });
  }
  return scored;
}

function scoredQuantity(line: StatLine, category: ValuedCategory, ratioBaselines: Record<string, number>): number {
  const ratio = RATIO_FIELDS[category.field];
  if (ratio) {
    const [makesField, attemptsField] = ratio;
    const attempts = line[attemptsField] ?? 0;
    if (attempts <= MIN_ATTEMPTS) return 0;
    return (line[makesField] ?? 0) - attempts * (ratioBaselines[category.statId] ?? 0);
  }
  return line[category.field] ?? 0;
}

/** Population mean and standard deviation, with the Python's guards for tiny pools. */
function meanAndStddev(values: number[]): [number, number] {
  if (!values.length) return [0, 1];
  const mean = values.reduce((sum, value) => sum + value, 0) / values.length;
  if (values.length < 2) return [mean, 1];
  const variance = values.reduce((sum, value) => sum + (value - mean) ** 2, 0) / values.length;
  return [mean, Math.sqrt(variance) || 1];
}

/** League baselines from a reference pool — normally every player rostered in the league,
 *  so "average" means an average rostered player, not an average NBA player. */
export function buildValuationContext(pool: StatLine[], categories: StatCategory[]): ValuationContext {
  const scored = scoringCategories(categories);
  const context: ValuationContext = {
    categories: scored,
    means: {},
    stddevs: {},
    ratioBaselines: {},
    poolSize: pool.length,
  };
  if (!pool.length) return context;

  // Ratio baselines first: they feed the scored quantity for those categories.
  for (const category of scored) {
    const ratio = RATIO_FIELDS[category.field];
    if (!ratio) continue;
    const [makesField, attemptsField] = ratio;
    const makes = pool.reduce((sum, line) => sum + (line[makesField] ?? 0), 0);
    const attempts = pool.reduce((sum, line) => sum + (line[attemptsField] ?? 0), 0);
    context.ratioBaselines[category.statId] = attempts > MIN_ATTEMPTS ? makes / attempts : 0;
  }

  for (const category of scored) {
    const [mean, stddev] = meanAndStddev(pool.map((line) => scoredQuantity(line, category, context.ratioBaselines)));
    context.means[category.statId] = mean;
    context.stddevs[category.statId] = stddev;
  }

  return context;
}

export function valuePlayer(line: StatLine, context: ValuationContext): CategoryZ {
  const z: CategoryZ = {};
  for (const category of context.categories) {
    const quantity = scoredQuantity(line, category, context.ratioBaselines);
    const mean = context.means[category.statId] ?? 0;
    const stddev = context.stddevs[category.statId] || 1;
    const score = (quantity - mean) / stddev;
    z[category.statId] = category.higherIsBetter ? score : -score;
  }
  return z;
}

/** Summed z across categories, leaving out any the manager is punting. */
export function totalValue(z: CategoryZ, punted: ReadonlySet<string> = new Set()): number {
  let total = 0;
  for (const [statId, value] of Object.entries(z)) {
    if (!punted.has(statId)) total += value;
  }
  return total;
}
