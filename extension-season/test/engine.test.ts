// Tests for the parts with no Python counterpart to check against: the schedule split,
// the early-season fallback chain, and the adds ranking.

import { describe, expect, it } from "vitest";

import { gameDatesFor, normalizeTeam, weekGames } from "../src/engine/schedule";
import { playerAverages } from "../src/engine/statWindows";
import { rankAdds } from "../src/engine/adds";
import { calculateProjectedPoints, type Totals } from "../src/engine/project";
import type { Feed, PlayersFile, ScheduleFile } from "../src/feed/types";
import type { StatCategory, YahooPlayer } from "../src/yahoo/types";

const schedule: ScheduleFile = {
  season: "2026-27",
  fields: ["home", "away", "game_id", "postponed"],
  game_count: 5,
  dates: {
    "2026-10-19": [["LAL", "GSW", "1", "N"]],
    "2026-10-20": [["BOS", "NYK", "2", "N"]],
    "2026-10-21": [["GSW", "PHX", "3", "N"]],
    "2026-10-22": [["LAL", "BOS", "4", "P"]],
    "2026-10-23": [["GSW", "SAC", "5", "N"]],
  },
};

const emptyPlayers: PlayersFile = {
  season: "2026-27", tail_days: 35, tail_start: "2026-09-15",
  fields: [], count: 0, players: {},
};

describe("schedule", () => {
  it("maps Yahoo's tricodes onto the NBA's", () => {
    expect(normalizeTeam("GS")).toBe("GSW");
    expect(normalizeTeam("no")).toBe("NOP");
    expect(normalizeTeam("PHX")).toBe("PHX");
  });

  it("counts home and away games and skips postponements", () => {
    expect(gameDatesFor(schedule, "GSW", "2026-10-19", "2026-10-23")).toEqual([
      "2026-10-19", "2026-10-21", "2026-10-23",
    ]);
    // LAL's only other game is postponed, so it does not count.
    expect(gameDatesFor(schedule, "LAL", "2026-10-19", "2026-10-23")).toEqual(["2026-10-19"]);
  });

  it("counts today once: banked when a box score exists, remaining when it does not", () => {
    const withBoxScore = weekGames(
      schedule, "GSW", "2026-10-19", "2026-10-23", "2026-10-21",
      new Set(["2026-10-19", "2026-10-21"]),
    );
    expect(withBoxScore).toMatchObject({ total: 3, played: 2, remaining: 1 });

    const tipoffPending = weekGames(
      schedule, "GSW", "2026-10-19", "2026-10-23", "2026-10-21",
      new Set(["2026-10-19"]),
    );
    expect(tipoffPending).toMatchObject({ total: 3, played: 1, remaining: 2 });
    expect(tipoffPending.remainingDates).toContain("2026-10-21");
  });
});

describe("early-season fallback", () => {
  const projections = {
    "201939": {
      name: "Test Player", team: "GSW", positions: "PG", confidence: 1,
      stats: {
        gp: 70, mpg: 32, fgm: 9, fga: 19, fg_pct: 0.47, ftm: 4, fta: 4.4, ft_pct: 0.9,
        threes: 4.5, points: 26, rebounds: 5, assists: 6, steals: 1.2, blocks: 0.3, turnovers: 3,
      },
    },
  };

  it("uses the preseason projection before a player has a sample", () => {
    const result = playerAverages({
      nbaId: "201939", mode: "season", today: "2026-10-21",
      players: emptyPlayers, playersPrev: emptyPlayers, projections,
    });

    expect(result.source).toBe("projection");
    expect(result.stats.points).toBe(26);
  });

  it("prefers last season's averages over nothing at all", () => {
    const prev: PlayersFile = {
      ...emptyPlayers,
      players: {
        "999": {
          name: "Journeyman",
          games: [],
          season_avg: {
            games_played: 54, fgm: 3, fga: 7, fg_pct: 0.42, ftm: 1, fta: 1.4, ft_pct: 0.75,
            threes: 1.1, points: 8.2, rebounds: 3.4, assists: 1.8, steals: 0.5, blocks: 0.2, turnovers: 1,
          },
        },
      },
    };

    const result = playerAverages({
      nbaId: "999", mode: "season", today: "2026-10-21",
      players: emptyPlayers, playersPrev: prev, projections: {},
    });

    expect(result.source).toBe("previous");
    expect(result.stats.points).toBeCloseTo(8.2);
  });

  it("reports an unknown player rather than inventing zeros silently", () => {
    const result = playerAverages({
      nbaId: null, mode: "season", today: "2026-10-21",
      players: emptyPlayers, playersPrev: emptyPlayers, projections: {},
    });

    expect(result.source).toBe("none");
    expect(result.stats.points).toBe(0);
  });
});

describe("best adds", () => {
  const categories: StatCategory[] = [
    { statId: "12", name: "Points", displayName: "PTS", sortOrder: "1", isDisplayOnly: false },
    { statId: "15", name: "Rebounds", displayName: "REB", sortOrder: "1", isDisplayOnly: false },
    { statId: "19", name: "Turnovers", displayName: "TO", sortOrder: "0", isDisplayOnly: false },
  ];

  const feed = {
    schedule,
    index: { count: 0, yahoo_to_nba: { "1001": "5001", "1002": "5002" }, nba_names: {} },
    players: emptyPlayers,
    playersPrev: emptyPlayers,
    projections: {
      season: "2026-27",
      count: 2,
      players: {
        "5001": {
          name: "Big Scorer", team: "GSW", positions: "SG", confidence: 1,
          stats: { fgm: 8, fga: 16, fg_pct: 0.5, ftm: 4, fta: 5, ft_pct: 0.8, threes: 3,
            points: 24, rebounds: 4, assists: 4, steals: 1, blocks: 0.4, turnovers: 2 },
        },
        "5002": {
          name: "Bench Guy", team: "LAL", positions: "C", confidence: 1,
          stats: { fgm: 1, fga: 3, fg_pct: 0.33, ftm: 0.5, fta: 1, ft_pct: 0.5, threes: 0.2,
            points: 3, rebounds: 2, assists: 0.5, steals: 0.2, blocks: 0.1, turnovers: 0.5 },
        },
      },
    },
  } as unknown as Feed;

  const team = (totals: Totals) => ({
    teamKey: "t", name: "t", current: totals, remaining: totals, combined: totals, players: [],
  });

  const freeAgents: YahooPlayer[] = [
    { playerKey: "p.1001", playerId: "1001", name: "Big Scorer", teamAbbr: "GSW",
      selectedPosition: "", eligiblePositions: ["SG"], status: "" },
    { playerKey: "p.1002", playerId: "1002", name: "Bench Guy", teamAbbr: "LAL",
      selectedPosition: "", eligiblePositions: ["C"], status: "" },
  ];

  it("ranks the player who flips a category above one who cannot", () => {
    // Trailing points by a hair, comfortably clear on rebounds and turnovers.
    const user = team({ "12": 500, "15": 300, "19": 60, _FGM: 0, _FGA: 0, _FTM: 0, _FTA: 0 });
    const opponent = team({ "12": 520, "15": 240, "19": 90, _FGM: 0, _FGA: 0, _FTM: 0, _FTA: 0 });

    const adds = rankAdds({
      feed, categories, user, opponent, freeAgents,
      weekStart: "2026-10-19", weekEnd: "2026-10-23", today: "2026-10-19", mode: "season",
    });

    expect(adds[0]?.name).toBe("Big Scorer");
    expect(adds[0]?.remainingGames).toBe(3);
    expect(adds[0]?.categoriesGained).toBe(1);
    expect(adds[0]?.flips).toContain("PTS");
  });

  it("counts the categories an add would cost you, not just the ones it wins", () => {
    // Same scorer, but now the turnover margin is thin enough for him to break it.
    const user = team({ "12": 500, "15": 300, "19": 60, _FGM: 0, _FGA: 0, _FTM: 0, _FTA: 0 });
    const opponent = team({ "12": 520, "15": 240, "19": 62, _FGM: 0, _FGA: 0, _FTM: 0, _FTA: 0 });

    const adds = rankAdds({
      feed, categories, user, opponent, freeAgents,
      weekStart: "2026-10-19", weekEnd: "2026-10-23", today: "2026-10-19", mode: "season",
    });

    const scorer = adds.find((add) => add.name === "Big Scorer");
    expect(scorer?.flips).toContain("PTS");
    expect(scorer?.costs).toContain("TO");
    expect(scorer?.categoriesGained).toBe(0);
  });

  it("skips players whose team has no games left this week", () => {
    const user = team({ "12": 500, "15": 300, "19": 60, _FGM: 0, _FGA: 0, _FTM: 0, _FTA: 0 });
    const adds = rankAdds({
      feed, categories, user, opponent: user, freeAgents,
      weekStart: "2026-10-19", weekEnd: "2026-10-23", today: "2026-10-23", mode: "season",
    });

    // Only GSW plays on the 23rd; LAL's man is dropped from the list entirely.
    expect(adds.map((add) => add.name)).toEqual(["Big Scorer"]);
  });
});

describe("category scoring guards", () => {
  it("treats turnovers as lower-is-better", () => {
    const categories: StatCategory[] = [
      { statId: "19", name: "Turnovers", displayName: "TO", sortOrder: "0", isDisplayOnly: false },
    ];
    const [a, b] = calculateProjectedPoints(categories, { "19": 50 }, { "19": 80 });
    expect(a.win).toBe(1);
    expect(b.loss).toBe(1);
  });

  it("ignores display-only categories such as FGM/A", () => {
    const categories: StatCategory[] = [
      { statId: "9004003", name: "FGM/A", displayName: "FGM/A", sortOrder: "1", isDisplayOnly: true },
      { statId: "12", name: "Points", displayName: "PTS", sortOrder: "1", isDisplayOnly: false },
    ];
    const [a] = calculateProjectedPoints(categories, { "9004003": 1, "12": 10 }, { "9004003": 99, "12": 5 });
    expect(a.win).toBe(1);
    expect(a.loss).toBe(0);
  });
});
