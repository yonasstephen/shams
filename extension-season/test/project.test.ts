// Banked stats: the matchup projection must start from what Yahoo already counted this
// week, live games included, even when the feed is days old.

import { describe, expect, it } from "vitest";

import { isOutStatus, projectMatchup, type TeamInput, type Totals } from "../src/engine/project";
import { parseStats } from "../src/yahoo/client";
import { todayIso } from "../src/content/context";
import type { Feed, GameRow, PlayersFile, ScheduleFile } from "../src/feed/types";
import type { StatCategory, YahooPlayer } from "../src/yahoo/types";

const categories: StatCategory[] = [
  { statId: "9004003", name: "Field Goals Made / Attempted", displayName: "FGM/A", sortOrder: "1", isDisplayOnly: true },
  { statId: "5", name: "Field Goal Percentage", displayName: "FG%", sortOrder: "1", isDisplayOnly: false },
  { statId: "10", name: "3-point Shots Made", displayName: "3PTM", sortOrder: "1", isDisplayOnly: false },
  { statId: "12", name: "Points Scored", displayName: "PTS", sortOrder: "1", isDisplayOnly: false },
];

// Golden State plays Tuesday, Thursday, Friday (today) and Sunday.
const schedule: ScheduleFile = {
  season: "2026-27",
  fields: ["home", "away", "game_id", "postponed"],
  game_count: 4,
  dates: {
    "2026-10-20": [["GSW", "LAC", "1", "N"]],
    "2026-10-22": [["PHX", "GSW", "2", "N"]],
    "2026-10-23": [["GSW", "SAC", "3", "N"]],
    "2026-10-25": [["DEN", "GSW", "4", "N"]],
  },
};

function players(games: Record<string, GameRow[]> = {}): PlayersFile {
  return {
    season: "2026-27", tail_days: 35, tail_start: "2026-09-15", fields: [], count: 0,
    players: Object.fromEntries(Object.entries(games).map(([id, rows]) => [id, { name: id, games: rows }])),
  };
}

const projection = {
  name: "Starter", team: "GSW", positions: "PG", confidence: 1,
  stats: { fgm: 8, fga: 16, fg_pct: 0.5, ftm: 2, fta: 2, ft_pct: 1, threes: 3,
    points: 24, rebounds: 4, assists: 6, steals: 1, blocks: 0, turnovers: 2 },
};

function feedWith(games: Record<string, GameRow[]> = {}): Feed {
  return {
    schedule,
    index: { count: 3, yahoo_to_nba: { "1001": "5001", "1002": "5002", "1003": "5003" }, nba_names: {} },
    players: players(games),
    playersPrev: players(),
    projections: {
      season: "2026-27", count: 3, players: { "5001": projection, "5002": projection, "5003": projection },
    },
  } as unknown as Feed;
}

function player(id: string, position: string, stats?: Record<string, number>): YahooPlayer {
  return {
    playerKey: `478.p.${id}`, playerId: id, name: `Player ${id}`, teamAbbr: "GS",
    selectedPosition: position, eligiblePositions: ["PG"], status: "", stats,
  };
}

const TODAY = "2026-10-23";

/** The starter (1001) plays every game; the backup (1002) sits on the bench. */
function week(todayLine: Record<string, number> | undefined): TeamInput["rosterByDate"] {
  return {
    "2026-10-20": [
      player("1001", "PG", { _FGM: 5, _FGA: 10, "5": 0.5, "10": 3, "12": 14 }),
      player("1002", "BN", { _FGM: 4, _FGA: 6, "5": 0.667, "10": 2, "12": 10 }),
    ],
    "2026-10-21": [player("1001", "PG"), player("1002", "BN")],
    "2026-10-22": [player("1001", "PG", { _FGM: 3, _FGA: 9, "10": 1, "12": 10 }), player("1002", "BN")],
    [TODAY]: [player("1001", "PG", todayLine), player("1002", "BN")],
  };
}

function project(team: Partial<TeamInput>, feed: Feed = feedWith()) {
  const input = (key: string): TeamInput => ({
    teamKey: key, name: key, rosterByDate: {}, optimize: false, ...team,
  });
  return projectMatchup({
    feed, categories, rosterPositions: ["PG", "BN"], weekStart: "2026-10-20", weekEnd: "2026-10-25",
    today: TODAY, mode: "season", teams: [input("mine"), input("theirs")],
  }).teams[0];
}

describe("banked stats", () => {
  it("come from Yahoo's daily lines when the feed has no games yet", () => {
    // Tonight's game is in progress: 1-for-4, one three.
    const mine = project({ rosterByDate: week({ _FGM: 1, _FGA: 4, "10": 1, "12": 3 }) });
    const starter = mine.players.find((p) => p.playerId === "1001")!;

    expect(starter.current["10"]).toBe(5);
    expect(starter.current["12"]).toBe(27);
    expect(starter.current["5"]).toBeCloseTo(9 / 23);
    expect(starter.playedGames).toBe(3);
    // Tonight is banked, so only Sunday is left to project.
    expect(starter.remainingGames).toBe(1);
    expect(mine.current["10"]).toBe(5);
    expect(mine.combined["10"]).toBe(5 + 3);
  });

  it("leave tonight's game to the projection until Yahoo has a line for it", () => {
    const mine = project({ rosterByDate: week(undefined) });
    const starter = mine.players.find((p) => p.playerId === "1001")!;

    expect(starter.current["10"]).toBe(4);
    expect(starter.remainingGames).toBe(2);
    expect(mine.combined["10"]).toBe(4 + 2 * 3);
  });

  it("skip a line scored on the bench", () => {
    const mine = project({ rosterByDate: week(undefined) });
    const backup = mine.players.find((p) => p.playerId === "1002")!;

    expect(backup.current["10"]).toBe(0);
    expect(backup.playedGames).toBe(0);
  });

  it("use Yahoo's week totals for the team, so they match the scoreboard", () => {
    const weekTotals: Totals = { _FGM: 108, _FGA: 243, "5": 0.444, "10": 31, "12": 315 };
    const mine = project({ rosterByDate: week(undefined), weekTotals });

    expect(mine.current["10"]).toBe(31);
    expect(mine.current["5"]).toBe(0.444);
    // Two games left for the starter: tonight and Sunday.
    expect(mine.combined["10"]).toBe(31 + 2 * 3);
    expect(mine.combined["5"]).toBeCloseTo((108 + 2 * 8) / (243 + 2 * 16));
  });

  it("fall back to the feed's box score for a day Yahoo sent no line", () => {
    const rows: GameRow[] = [["2026-10-20", 30, 6, 12, 2, 2, 4, 18, 5, 3, 1, 0, 2]];
    const rosterByDate = Object.fromEntries(
      Object.entries(week(undefined)).map(([date, roster]) => [
        date, roster.map((entry) => ({ ...entry, stats: undefined })),
      ]),
    );
    const mine = project({ rosterByDate }, feedWith({ "5001": rows }));
    const starter = mine.players.find((p) => p.playerId === "1001")!;

    expect(starter.current["10"]).toBe(4);
    expect(starter.current["12"]).toBe(18);
    expect(starter.current["5"]).toBeCloseTo(0.5);
  });
});

describe("remaining games", () => {
  const SUNDAY = "2026-10-25";
  const find = (mine: ReturnType<typeof project>, id: string) => mine.players.find((p) => p.playerId === id)!;

  it("project only the days a player is in an active slot", () => {
    // Sunday's lineup swaps them: the starter sits and the backup starts.
    const mine = project({
      rosterByDate: { ...week(undefined), [SUNDAY]: [player("1001", "BN"), player("1002", "PG")] },
    });
    const starter = find(mine, "1001");
    const backup = find(mine, "1002");

    expect(starter.projectedGames).toBe(1); // tonight only
    expect(backup.projectedGames).toBe(1); // Sunday only
    expect(mine.remaining["10"]).toBe(2 * 3);
  });

  it("still show every game left, and which of them are on the bench", () => {
    const mine = project({
      rosterByDate: { ...week(undefined), [SUNDAY]: [player("1001", "BN"), player("1002", "PG")] },
    });
    const starter = find(mine, "1001");
    const backup = find(mine, "1002");

    expect([starter.remainingGames, starter.totalGames]).toEqual([2, 4]);
    expect(starter.benchedDates).toEqual([SUNDAY]);
    expect([backup.remainingGames, backup.totalGames]).toEqual([2, 4]);
    expect(backup.benchedDates).toEqual([TODAY]);
  });

  it("use today's lineup for a day Yahoo sent none for", () => {
    const mine = project({ rosterByDate: { ...week(undefined), [SUNDAY]: [] } });

    expect(find(mine, "1001").projectedGames).toBe(2);
    expect(find(mine, "1002").projectedGames).toBe(0);
    expect(find(mine, "1002").benchedDates).toEqual([TODAY, SUNDAY]);
  });

  it("include a player added for a day still to come", () => {
    const mine = project({
      rosterByDate: {
        ...week(undefined),
        [SUNDAY]: [player("1001", "PG"), player("1002", "BN"), player("1003", "Util")],
      },
    });
    const added = find(mine, "1003");

    expect([added.remainingGames, added.projectedGames]).toEqual([1, 1]);
    expect(added.addedOn).toBe(SUNDAY);
    expect(added.playedGames).toBe(0);
    expect(mine.remaining["10"]).toBe(3 * 3); // the starter twice, the new player once
  });

  it("keep a dropped player's banked games but nothing after he left", () => {
    // 1003 started Tuesday and was dropped before Thursday.
    const rosterByDate = week(undefined);
    rosterByDate["2026-10-20"]!.push(player("1003", "Util", { _FGM: 2, _FGA: 5, "10": 2, "12": 6 }));
    rosterByDate["2026-10-21"]!.push(player("1003", "Util"));
    const mine = project({ rosterByDate });
    const dropped = find(mine, "1003");

    expect(dropped.current["10"]).toBe(2);
    expect(dropped.playedGames).toBe(1);
    expect([dropped.remainingGames, dropped.projectedGames]).toEqual([0, 0]);
    expect(dropped.droppedOn).toBe("2026-10-22");
    expect(dropped.addedOn).toBeUndefined();
  });

  it("count tonight for a player dropped from tomorrow on", () => {
    const mine = project({ rosterByDate: { ...week(undefined), [SUNDAY]: [player("1001", "PG")] } });
    const backup = find(mine, "1002");

    expect(backup.remainingGames).toBe(1); // tonight, on the bench
    expect(backup.benchedDates).toEqual([TODAY]);
    expect(backup.droppedOn).toBe(SUNDAY);
  });
});

describe("isOutStatus", () => {
  it("treats injured and suspended players as out, but not game-time decisions", () => {
    expect(isOutStatus("O")).toBe(true);
    expect(isOutStatus("INJ")).toBe(true);
    expect(isOutStatus("SUSP")).toBe(true);
    expect(isOutStatus("GTD")).toBe(false);
    expect(isOutStatus("")).toBe(false);
  });
});

describe("parseStats", () => {
  it("splits FGM/A and FTM/A into makes and attempts", () => {
    const stats = parseStats([
      { stat_id: "9004003", value: "108/243" },
      { stat_id: "5", value: ".444" },
      { stat_id: "9007006", value: "0/0" },
      { stat_id: "8", value: "-" },
      { stat_id: "10", value: 31 },
    ]);

    expect(stats).toEqual({ _FGM: 108, _FGA: 243, "5": 0.444, _FTM: 0, _FTA: 0, "10": 31 });
  });

  it("reads a day of dashes as no line at all", () => {
    expect(
      parseStats([
        { stat_id: "9004003", value: "-/-" },
        { stat_id: "5", value: "-" },
        { stat_id: "12", value: "-" },
      ]),
    ).toBeUndefined();
  });
});

describe("todayIso", () => {
  it("follows US Eastern time, not the browser's", () => {
    // Saturday morning in Singapore is still Friday night's games in New York.
    expect(todayIso(new Date("2026-10-24T01:23:00Z"))).toBe("2026-10-23");
    expect(todayIso(new Date("2026-10-24T04:30:00Z"))).toBe("2026-10-24");
  });
});
