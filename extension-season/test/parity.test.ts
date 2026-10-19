// Parity with the Python engine.
//
// The fixtures here are written by tools/tests/test_engine_parity.py — Python computes
// the answers, TypeScript has to match them. Regenerate the fixtures whenever the
// projection math changes on either side:
//
//   cd tools/tests && pipenv run pytest test_engine_parity.py -v

import { describe, expect, it } from "vitest";

import categoryScoring from "./fixtures/category-scoring.json";
import rosterOptimizer from "./fixtures/roster-optimizer.json";
import teamTotals from "./fixtures/team-totals.json";
import statWindows from "./fixtures/stat-windows.json";
import nameNormalization from "./fixtures/name-normalization.json";
import valuation from "./fixtures/valuation.json";

import { calculateProjectedPoints, sumContributions, type Totals } from "../src/engine/project";
import { buildValuationContext, totalValue, valuePlayer } from "../src/engine/valuation";
import { optimizeRosterPositions } from "../src/engine/rosterOptimizer";
import { playerAverages } from "../src/engine/statWindows";
import { normalizePlayerName } from "../src/engine/playerIdentity";
import type { GameRow, PlayersFile, StatLine } from "../src/feed/types";
import type { StatCategory } from "../src/yahoo/types";

interface RawStat {
  stat_id: string;
  display_name: string;
  name: string;
  sort_order: string;
  is_only_display_stat?: number;
}

function toCategories(raw: RawStat[]): StatCategory[] {
  return raw.map((stat) => ({
    statId: stat.stat_id,
    name: stat.name,
    displayName: stat.display_name,
    sortOrder: stat.sort_order,
    isDisplayOnly: stat.is_only_display_stat === 1,
  }));
}

describe("category scoring", () => {
  const categories = toCategories(categoryScoring.statMeta as RawStat[]);

  for (const testCase of categoryScoring.cases) {
    it(`matches Python: ${testCase.name}`, () => {
      const [a, b] = calculateProjectedPoints(
        categories,
        testCase.teamA as Totals,
        testCase.teamB as Totals,
      );

      expect(a).toEqual(testCase.expected.a);
      expect(b).toEqual(testCase.expected.b);
    });
  }
});

describe("roster optimizer", () => {
  for (const testCase of rosterOptimizer.cases) {
    it(`matches Python: ${testCase.name}`, () => {
      const assignments = optimizeRosterPositions(
        testCase.players.map((player) => ({
          playerKey: player.player_key,
          eligiblePositions: player.eligible_positions,
        })),
        testCase.roster_positions,
        new Set(testCase.with_games),
        testCase.ranks as Record<string, number>,
      );

      expect(assignments).toEqual(testCase.expected);
    });
  }
});

describe("team totals", () => {
  it("pools shooting volume the way Python does", () => {
    const categories = toCategories(teamTotals.statMeta as RawStat[]);
    const contributions = teamTotals.playerContributions as Record<string, Record<string, number>>;
    const shooting = teamTotals.playerShooting as Record<string, Record<string, number>>;

    const lines: Totals[] = Object.entries(contributions).map(([playerKey, stats]) => ({
      ...stats,
      _FGM: shooting[playerKey]?.["fgm"] ?? 0,
      _FGA: shooting[playerKey]?.["fga"] ?? 0,
      _FTM: shooting[playerKey]?.["ftm"] ?? 0,
      _FTA: shooting[playerKey]?.["fta"] ?? 0,
    }));

    const totals = sumContributions(lines, categories);

    for (const [statId, expected] of Object.entries(teamTotals.expected as Record<string, number>)) {
      expect(totals[statId], `stat ${statId}`).toBeCloseTo(expected, 9);
    }
  });
});

describe("stat windows", () => {
  const today = statWindows.today;

  for (const testCase of statWindows.cases) {
    const players: PlayersFile = {
      season: statWindows.season,
      tail_days: 400,
      tail_start: "2000-01-01",
      fields: statWindows.fields,
      count: 1,
      players: {
        [testCase.nbaId]: { name: testCase.name, games: testCase.games as GameRow[] },
      },
    };
    const empty: PlayersFile = { ...players, count: 0, players: {} };

    for (const [mode, expected] of Object.entries(testCase.expected as Record<string, StatLine>)) {
      // "season" in Python averages every cached game; the feed's equivalent is the
      // precomputed season average, so the window path covers the last* modes only.
      if (mode === "season") continue;

      it(`${testCase.name} ${mode} matches Python`, () => {
        const result = playerAverages({
          nbaId: testCase.nbaId,
          mode: mode as "last3" | "last7" | "last7d" | "last30d",
          today,
          players,
          playersPrev: empty,
          projections: {},
        });

        expect(result.source).toBe("window");
        for (const field of [
          "fgm", "fga", "fg_pct", "ftm", "fta", "ft_pct", "threes",
          "points", "rebounds", "assists", "steals", "blocks", "turnovers",
        ] as const) {
          expect(result.stats[field], `${mode} ${field}`).toBeCloseTo(expected[field], 6);
        }
      });
    }
  }
});

describe("name normalization", () => {
  // A disagreement here means a player silently projects as zeros, so it is checked
  // character for character against Python's normalize_player_name.
  for (const testCase of nameNormalization.cases) {
    it(`matches Python: ${testCase.input.trim()}`, () => {
      expect(normalizePlayerName(testCase.input)).toBe(testCase.expected);
    });
  }
});

describe("valuation", () => {
  // value_model.py chooses its reference pool by Yahoo rank; the extension's pool is the
  // league's rostered players, so the fixture names the pool and both sides score it.
  const categories = toCategories(valuation.statMeta as RawStat[]);
  const lines = Object.fromEntries(valuation.cases.map((testCase) => [testCase.id, testCase.line as StatLine]));
  const context = buildValuationContext(
    valuation.pool.map((id) => lines[id] as StatLine),
    categories,
  );

  it("builds the same league baselines", () => {
    for (const [field, expected] of [
      ["ratioBaselines", valuation.context.ratioBaselines],
      ["means", valuation.context.means],
      ["stddevs", valuation.context.stddevs],
    ] as const) {
      for (const [statId, value] of Object.entries(expected as Record<string, number>)) {
        expect(context[field][statId], `${field} ${statId}`).toBeCloseTo(value, 9);
      }
    }
  });

  for (const testCase of valuation.cases) {
    it(`matches Python: ${testCase.id}`, () => {
      const z = valuePlayer(testCase.line as StatLine, context);
      for (const [statId, expected] of Object.entries(testCase.expected.z as Record<string, number>)) {
        expect(z[statId], `stat ${statId}`).toBeCloseTo(expected, 9);
      }
      expect(Object.keys(z).sort()).toEqual(Object.keys(testCase.expected.z).sort());
      expect(totalValue(z)).toBeCloseTo(testCase.expected.total, 9);
      expect(totalValue(z, new Set(valuation.punt))).toBeCloseTo(testCase.expected.totalPunting, 9);
    });
  }
});
