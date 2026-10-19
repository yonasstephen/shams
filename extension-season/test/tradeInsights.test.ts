// Tests for the trade insights: the rest-of-season blend, daily lineups and the league
// profile. None of these has a Python counterpart, so the expected numbers are worked out
// by hand from small leagues.

import { describe, expect, it } from "vitest";

import { blendLines, restOfSeasonAverages } from "../src/engine/statWindows";
import { bestLineup } from "../src/engine/lineup";
import { gradeFor, profileLeague, standings } from "../src/engine/teamProfile";
import type { Feed, PlayersFile, ProjectionEntry, ScheduleFile, StatLine } from "../src/feed/types";
import type { LeagueRoster, StatCategory, YahooPlayer } from "../src/yahoo/types";

const emptyPlayers: PlayersFile = {
  season: "2026-27", tail_days: 35, tail_start: "2026-09-15", fields: [], count: 0, players: {},
};

function line(points: number, rebounds: number, turnovers: number, fgm: number, fga: number): StatLine {
  return {
    fgm, fga, fg_pct: fga ? fgm / fga : 0, ftm: 2, fta: 2.5, ft_pct: 0.8, threes: 1,
    points, rebounds, assists: 2, steals: 1, blocks: 0.5, turnovers,
  };
}

describe("rest-of-season blend", () => {
  const projected = line(20, 6, 2, 8, 16);
  const season = { ...line(30, 6, 2, 12, 20), games_played: 25 };

  it("weights the season by games played against the prior's games", () => {
    // 25 games against a prior worth 25: an even split.
    const blended = blendLines(season, 25, projected, 25);
    expect(blended.points).toBeCloseTo(25);
    // FG% comes from the blended makes and attempts, not an average of the two rates.
    expect(blended.fg_pct).toBeCloseTo(10 / 18);
  });

  it("leans on the projection early and on the season late", () => {
    const early = restOfSeasonAverages({
      nbaId: "1",
      players: { ...emptyPlayers, players: { "1": { name: "P", games: [], season_avg: { ...season, games_played: 5 } } } },
      playersPrev: emptyPlayers,
      projections: { "1": { name: "P", team: "GSW", positions: "PG", confidence: 1, stats: projected } },
    });
    expect(early.source).toBe("blend");
    expect(early.stats.points).toBeCloseTo(20 + (10 * 5) / 30);
  });

  it("falls back to last season when the projection missed a player", () => {
    const result = restOfSeasonAverages({
      nbaId: "2",
      players: emptyPlayers,
      playersPrev: { ...emptyPlayers, players: { "2": { name: "Q", games: [], season_avg: { ...line(9, 3, 1, 3, 7), games_played: 60 } } } },
      projections: {},
    });
    expect(result.source).toBe("previous");
    expect(result.stats.points).toBe(9);
  });

  it("uses the season alone when there is nothing to shrink toward", () => {
    const result = restOfSeasonAverages({
      nbaId: "3",
      players: { ...emptyPlayers, players: { "3": { name: "R", games: [], season_avg: { ...line(14, 5, 1, 5, 11), games_played: 4 } } } },
      playersPrev: emptyPlayers,
      projections: {},
    });
    expect(result.source).toBe("season");
    expect(result.stats.points).toBe(14);
  });
});

describe("best lineup", () => {
  it("moves an earlier starter to make room for the next-best player", () => {
    // The guard can play either slot; the point guard only one. Best-first would park the
    // guard at PG and bench the point guard unless it shuffles.
    const lineup = bestLineup(
      [
        { key: "guard", eligiblePositions: ["PG", "SG"], value: 10 },
        { key: "pg", eligiblePositions: ["PG"], value: 8 },
      ],
      ["PG", "SG", "BN"],
    );
    expect(lineup.get("pg")).toBe("PG");
    expect(lineup.get("guard")).toBe("SG");
  });

  it("sits the least valuable player when the slots run out", () => {
    const lineup = bestLineup(
      [
        { key: "a", eligiblePositions: ["C"], value: 1 },
        { key: "b", eligiblePositions: ["C"], value: 5 },
        { key: "c", eligiblePositions: ["PG"], value: -2 },
      ],
      ["C", "PG", "BN", "IL"],
    );
    expect([...lineup.keys()].sort()).toEqual(["b", "c"]);
  });

  it("credits a specific slot before Util", () => {
    const lineup = bestLineup([{ key: "a", eligiblePositions: ["SF", "F", "Util"], value: 3 }], ["Util", "SF"]);
    expect(lineup.get("a")).toBe("SF");
  });
});

describe("standings", () => {
  it("shares a rank between ties and splits the win between them", () => {
    expect(standings([10, 10, 4], false)).toEqual([
      { rank: 1, winShare: 0.75 },
      { rank: 1, winShare: 0.75 },
      { rank: 3, winShare: 0 },
    ]);
  });

  it("reads turnovers the right way round", () => {
    expect(standings([12, 8], true).map((row) => row.rank)).toEqual([2, 1]);
  });

  it("grades in thirds, the middle taking the remainder", () => {
    const grades = Array.from({ length: 10 }, (_, index) => gradeFor(index + 1, 10));
    expect(grades.filter((grade) => grade === "strong")).toHaveLength(3);
    expect(grades.filter((grade) => grade === "neutral")).toHaveLength(4);
    expect(grades.filter((grade) => grade === "weak")).toHaveLength(3);
  });
});

describe("league profile", () => {
  const categories: StatCategory[] = [
    { statId: "5", name: "Field Goal Percentage", displayName: "FG%", sortOrder: "1", isDisplayOnly: false },
    { statId: "12", name: "Points", displayName: "PTS", sortOrder: "1", isDisplayOnly: false },
    { statId: "15", name: "Rebounds", displayName: "REB", sortOrder: "1", isDisplayOnly: false },
    { statId: "19", name: "Turnovers", displayName: "TO", sortOrder: "0", isDisplayOnly: false },
    { statId: "9004003", name: "FGM/A", displayName: "FGM/A", sortOrder: "1", isDisplayOnly: true },
  ];

  // AAA plays Monday, Wednesday, Friday; BBB Tuesday, Thursday, Saturday.
  const schedule: ScheduleFile = {
    season: "2026-27",
    fields: ["home", "away", "game_id", "postponed"],
    game_count: 6,
    dates: {
      "2026-11-02": [["AAA", "ZZZ", "1", "N"]],
      "2026-11-03": [["BBB", "ZZZ", "2", "N"]],
      "2026-11-04": [["ZZZ", "AAA", "3", "N"]],
      "2026-11-05": [["BBB", "ZZZ", "4", "N"]],
      "2026-11-06": [["AAA", "ZZZ", "5", "N"]],
      "2026-11-07": [["ZZZ", "BBB", "6", "N"]],
    },
  };

  const projections: Record<string, ProjectionEntry> = {};
  const roster = (players: [string, string, string, "PG" | "C", StatLine, string?][]): YahooPlayer[] =>
    players.map(([id, name, team, position, stats, slot]) => {
      projections[id] = { name, team, positions: position, confidence: 1, stats };
      return {
        playerKey: `p.${id}`, playerId: id, name, teamAbbr: team,
        selectedPosition: slot ?? position,
        eligiblePositions: position === "PG" ? ["PG", "G", "Util"] : ["C", "Util"],
        status: "",
      };
    });

  const rosters: LeagueRoster[] = [
    {
      teamKey: "t.1", teamId: "1", name: "Scorers", manager: "a",
      players: roster([
        ["1", "Scorer One", "AAA", "PG", line(30, 3, 3, 10, 20)],
        ["2", "Scorer Two", "BBB", "PG", line(25, 4, 2.5, 9, 19)],
        ["9", "Bench Guard", "AAA", "PG", line(5, 1, 1, 2, 6), "BN"],
      ]),
    },
    {
      teamKey: "t.2", teamId: "2", name: "Bigs", manager: "b",
      players: roster([
        ["3", "Big One", "AAA", "C", line(12, 13, 1.5, 5, 8)],
        ["4", "Big Two", "BBB", "C", line(10, 11, 1, 4, 7)],
        ["8", "Spare Big", "AAA", "C", line(6, 6, 0.5, 2, 4), "BN"],
      ]),
    },
    {
      teamKey: "t.3", teamId: "3", name: "Middle", manager: "c",
      players: roster([
        ["5", "Mid One", "AAA", "PG", line(18, 7, 2, 7, 15)],
        ["6", "Mid Two", "BBB", "C", line(16, 8, 2, 6, 12)],
        ["7", "Star On IL", "AAA", "PG", line(35, 10, 3, 12, 22), "IL"],
      ]),
    },
  ];

  const feed = {
    schedule,
    index: {
      count: 9,
      yahoo_to_nba: Object.fromEntries(Object.keys(projections).map((id) => [id, id])),
      nba_names: {},
    },
    players: emptyPlayers,
    playersPrev: emptyPlayers,
    projections: { season: "2026-27", count: 9, players: projections },
  } as unknown as Feed;

  const profile = profileLeague({
    feed,
    categories,
    rosterPositions: ["PG", "C", "BN", "BN", "IL"],
    rosters,
    today: "2026-11-02",
    horizonStart: "2026-11-02",
    horizonEnd: "2026-11-08",
    mode: "ros",
  });
  const team = (name: string) => profile.teams.find((entry) => entry.name === name)!;
  const category = (name: string, display: string) => team(name).categories.find((row) => row.displayName === display)!;

  it("plays the best lineup every day: bench players sit, IL players never start", () => {
    // One PG slot: the bench guard shares Scorer One's schedule and never gets in.
    expect(team("Scorers").players.find((p) => p.name === "Bench Guard")?.starts).toBe(0);
    expect(team("Scorers").players.find((p) => p.name === "Scorer One")?.starts).toBe(3);
    // The spare big benches behind Big One on the same nights.
    expect(team("Bigs").players.find((p) => p.name === "Spare Big")?.starts).toBe(0);

    const star = team("Middle").players.find((p) => p.name === "Star On IL")!;
    expect(star.injured).toBe(true);
    expect(star.starts).toBe(0);
  });

  it("sums the starters into weekly totals with pooled shooting", () => {
    expect(category("Scorers", "PTS").weekly).toBeCloseTo(3 * 30 + 3 * 25);
    expect(category("Bigs", "REB").weekly).toBeCloseTo(3 * 13 + 3 * 11);
    // The IL star contributes nothing: Middle is exactly its two healthy players.
    expect(category("Middle", "PTS").weekly).toBeCloseTo(3 * 18 + 3 * 16);
    expect(category("Bigs", "FG%").weekly).toBeCloseTo(27 / 45);
  });

  it("ranks and grades every team in every category, turnovers inverted", () => {
    expect(category("Scorers", "PTS")).toMatchObject({ rank: 1, grade: "strong", winShare: 1 });
    expect(category("Scorers", "REB")).toMatchObject({ rank: 3, grade: "weak", winShare: 0 });
    expect(category("Bigs", "TO")).toMatchObject({ rank: 1, grade: "strong" });
    expect(category("Middle", "FG%")).toMatchObject({ rank: 3, grade: "weak" });
    // Display-only stats are not categories.
    expect(team("Scorers").categories.map((row) => row.displayName)).toEqual(["FG%", "PTS", "REB", "TO"]);
  });

  it("lists needs weakest first, padded with neutral categories", () => {
    expect(team("Scorers").needs.map((row) => row.displayName)).toEqual(["REB", "TO", "FG%"]);
  });

  it("orders the league by expected categories won", () => {
    expect(profile.teams.map((entry) => entry.name)).toEqual(["Bigs", "Middle", "Scorers"]);
    expect(team("Bigs").expectedWins).toBeCloseTo(3);
    expect(team("Middle").rank).toBe(2);
    expect(team("Scorers").rank).toBe(2);
    // Every pairing hands out one category's worth of wins, so the league sums to C × N / 2.
    const total = profile.teams.reduce((sum, entry) => sum + entry.expectedWins, 0);
    expect(total).toBeCloseTo((4 * 3) / 2);
  });

  it("ranks slot strength by value above replacement, so an empty slot ranks last", () => {
    expect(profile.slotTypes).toEqual(["PG", "C"]);
    // Neither team has anyone who can play the slot, however good the rest of the roster.
    expect(team("Bigs").slots.find((row) => row.slot === "PG")).toMatchObject({ rank: 3, value: 0, grade: "weak" });
    expect(team("Scorers").slots.find((row) => row.slot === "C")).toMatchObject({ rank: 3, value: 0 });

    // Replacement is the worst rostered player, so every started game adds value.
    const all = profile.teams.flatMap((entry) => entry.players);
    const replacement = Math.min(...all.map((player) => player.value));
    const scorers = team("Scorers").players;
    const starterValue = (name: string) => scorers.find((p) => p.name === name)!.value - replacement;
    expect(team("Scorers").slots.find((row) => row.slot === "PG")?.value).toBeCloseTo(
      3 * starterValue("Scorer One") + 3 * starterValue("Scorer Two"),
    );
  });

  it("measures the horizon in weeks", () => {
    expect(profile.horizon).toMatchObject({ days: 7, weeks: 1 });
  });
});
