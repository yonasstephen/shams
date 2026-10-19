// Player form on the Transactions page. Window and minute-trend arithmetic is pinned to
// Python in parity.test.ts; these cover what the parity cases cannot reach: the season
// average path, last season's fallback, empty windows and the panel's sort order.

import { describe, expect, it } from "vitest";

import { minuteTrend, playerForm, windowRows } from "../src/engine/playerForm";
import { sortRows, type FormRow } from "../src/overlay/transactionsPanel";
import type { GameRow, PlayerEntry, StatLine } from "../src/feed/types";

/** [date, min, fgm, fga, ftm, fta, threes, points, rebounds, assists, steals, blocks, turnovers] */
function game(date: string, minutes: number, points: number, fgm = 4, fga = 10): GameRow {
  return [date, minutes, fgm, fga, 2, 2, 1, points, 5, 3, 1, 0, 2];
}

const sat = (date: string): GameRow => [date, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0];

const seasonAverage: StatLine = {
  games_played: 20, mpg: 30, fgm: 6, fga: 12, fg_pct: 0.5, ftm: 3, fta: 4, ft_pct: 0.75,
  threes: 2, points: 17, rebounds: 6, assists: 4, steals: 1, blocks: 0.5, turnovers: 2,
};

const entry: PlayerEntry = {
  name: "P",
  games: [
    game("2026-11-01", 20, 10),
    game("2026-11-03", 24, 12),
    sat("2026-11-05"),
    game("2026-11-07", 30, 18),
    game("2026-11-09", 34, 22, 9, 15),
    // After "today": a historical feed never ships these, but they must not count.
    game("2026-11-12", 40, 40),
  ],
  season_avg: seasonAverage,
};

const today = "2026-11-10";

describe("player form windows", () => {
  it("counts a game he sat as a game, as the web app does", () => {
    const form = playerForm({ entry, previous: undefined, window: "last3", aggregation: "avg", today });
    expect(form.games).toBe(3);
    expect(form.dnp).toBe(1);
    expect(form.stats?.points).toBeCloseTo((0 + 18 + 22) / 3);
    expect(form.minutes).toBeCloseTo((0 + 30 + 34) / 3);
    // Shooting from summed makes and attempts: 13 of 25, the zero game adding nothing.
    expect(form.stats?.fg_pct).toBeCloseTo(13 / 25);
  });

  it("sums instead of averaging when asked", () => {
    const form = playerForm({ entry, previous: undefined, window: "last3", aggregation: "sum", today });
    expect(form.stats?.points).toBe(40);
    expect(form.minutes).toBe(64);
    expect(form.stats?.fg_pct).toBeCloseTo(13 / 25);
  });

  it("includes the cutoff day in a day window and nothing after today", () => {
    // Seven days before 11-10 is 11-03, which counts.
    expect(windowRows(entry.games, "last7d", today).map((row) => row[0])).toEqual([
      "2026-11-09", "2026-11-07", "2026-11-05", "2026-11-03",
    ]);
    expect(windowRows(entry.games, "last", today).map((row) => row[0])).toEqual(["2026-11-09"]);
  });

  it("reports the last game he played, not the last one he sat", () => {
    const form = playerForm({ entry, previous: undefined, window: "last", aggregation: "avg", today: "2026-11-06" });
    expect(form.stats?.points).toBe(0);
    expect(form.dnp).toBe(1);
    expect(form.lastPlayed).toBe("2026-11-03");
  });

  it("returns no stats, but keeps the last game played, when the window is empty", () => {
    const form = playerForm({ entry, previous: undefined, window: "last7d", aggregation: "avg", today: "2026-12-31" });
    expect(form.stats).toBeNull();
    expect(form.games).toBe(0);
    expect(form.source).toBe("window");
    expect(form.lastPlayed).toBe("2026-11-12");
  });

  it("says none for a player the feed has never heard of", () => {
    const form = playerForm({ entry: undefined, previous: undefined, window: "last7", aggregation: "avg", today });
    expect(form.source).toBe("none");
    expect(form.stats).toBeNull();
    expect(form.trend).toBeNull();
  });
});

describe("season window", () => {
  it("reads the season average, minutes included, and scales it for totals", () => {
    const average = playerForm({ entry, previous: undefined, window: "season", aggregation: "avg", today });
    expect(average.source).toBe("season");
    expect(average.games).toBe(20);
    expect(average.dnp).toBeNull();
    expect(average.minutes).toBe(30);
    expect(average.stats?.points).toBe(17);

    const total = playerForm({ entry, previous: undefined, window: "season", aggregation: "sum", today });
    expect(total.stats?.points).toBe(340);
    expect(total.minutes).toBe(600);
    expect(total.stats?.fg_pct).toBe(0.5);
  });

  it("falls back to last season before this season has a game", () => {
    const previous: PlayerEntry = { name: "P", games: [], season_avg: { ...seasonAverage, mpg: undefined } };
    const form = playerForm({
      entry: { name: "P", games: [] }, previous, window: "season", aggregation: "avg", today,
    });
    expect(form.source).toBe("previous");
    expect(form.stats?.points).toBe(17);
    // A feed built before season minutes were added has none to show.
    expect(form.minutes).toBeNull();
  });
});

describe("minute trend", () => {
  it("compares the last game played with the three played before it", () => {
    // Played, newest first: 34, 30, 24, 20 — the game he sat is skipped.
    const trend = minuteTrend(entry.games, today);
    expect(trend?.last).toBe(34);
    expect(trend?.priorAverage).toBeCloseTo((30 + 24 + 20) / 3);
    expect(trend?.delta).toBeCloseTo(34 - 24.6667, 3);
  });

  it("treats a first game as all trend, as Python does", () => {
    const trend = minuteTrend([game("2026-11-01", 22, 8)], today);
    expect(trend).toEqual({ last: 22, priorAverage: 0, delta: 22 });
  });
});

describe("form table sort", () => {
  function row(order: number, name: string, minutes: number | null): FormRow {
    const form = playerForm({
      entry: minutes === null ? undefined : { name, games: [game("2026-11-09", minutes, 10)] },
      previous: undefined,
      window: "last",
      aggregation: "avg",
      today,
    });
    return { order, matched: minutes !== null, form, player: { name } as FormRow["player"] };
  }

  const rows = [row(0, "B", 20), row(1, "A", null), row(2, "C", 35)];

  it("sorts by a stat with players lacking it at the bottom either way", () => {
    expect(sortRows(rows, { column: "minutes", descending: true }).map((r) => r.player.name)).toEqual(["C", "B", "A"]);
    expect(sortRows(rows, { column: "minutes", descending: false }).map((r) => r.player.name)).toEqual(["B", "C", "A"]);
  });

  it("returns to Yahoo's order", () => {
    expect(sortRows(rows, { column: "order", descending: false }).map((r) => r.player.name)).toEqual(["B", "A", "C"]);
  });
});
