// Yahoo Fantasy read client, authenticated by the browser session.
//
// Runs inside a content script on basketball.fantasysports.yahoo.com, where
// `credentials: "include"` carries the user's own Yahoo cookies. No OAuth app, no
// consumer key, no server — which is the entire point of this extension.

import { asArray, num, pick, str, unwrap } from "./shapes";
import type {
  LeagueRoster,
  LeagueSettings,
  Matchup,
  RosterPosition,
  StatCategory,
  YahooPlayer,
  YahooTeam,
} from "./types";

const BASE = "https://pub-api-rw.fantasysports.yahoo.com/fantasy/v2";

export class YahooShapeError extends Error {}

async function get(path: string): Promise<unknown> {
  const separator = path.includes("?") ? "&" : "?";
  const response = await fetch(`${BASE}${path}${separator}format=json_f`, {
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error(`Yahoo ${response.status} for ${path}`);
  }
  return response.json();
}

/** The active NBA game key, read from the user's own game list rather than hardcoded —
 *  it changes every season and a stale literal silently projects the wrong year. */
export async function fetchGameKey(): Promise<string> {
  const data = await get("/users;use_login=1/games;game_codes=nba");
  const users = unwrap(pick(data, "fantasy_content", "users"), "user");
  const games = unwrap(pick(users[0], "games"), "game");

  const live = games.filter((game) => str(game["game_key"]) && num(game["is_game_over"]) !== 1);
  const candidates = live.length ? live : games;
  const latest = candidates
    .slice()
    .sort((a, b) => num(a["game_id"]) - num(b["game_id"]))
    .pop();

  const key = str(latest?.["game_key"]);
  if (!key) throw new YahooShapeError("could not find an NBA game key on this account");
  return key;
}

function parseStatCategories(settings: unknown): StatCategory[] {
  const stats = unwrap(pick(settings, "stat_categories", "stats"), "stat");
  return stats.map((stat) => ({
    statId: str(stat["stat_id"]),
    name: str(stat["name"]),
    displayName: str(stat["display_name"]) || str(stat["name"]),
    sortOrder: str(stat["sort_order"]),
    isDisplayOnly: num(stat["is_only_display_stat"]) === 1,
  }));
}

function parseRosterPositions(settings: unknown): RosterPosition[] {
  const positions = unwrap(pick(settings, "roster_positions"), "roster_position");
  return positions.map((entry) => ({
    position: str(entry["position"]),
    count: num(entry["count"]),
  }));
}

export async function fetchLeagueSettings(leagueKey: string): Promise<LeagueSettings> {
  const data = await get(`/league/${leagueKey};out=settings`);
  const league = pick(data, "fantasy_content", "league");
  const settings = pick(league, "settings");

  const statCategories = parseStatCategories(settings);
  if (!statCategories.length) {
    throw new YahooShapeError(`no stat categories in the settings for ${leagueKey}`);
  }

  return {
    leagueKey,
    name: str(pick(league, "name")),
    statCategories,
    rosterPositions: parseRosterPositions(settings),
    currentWeek: num(pick(league, "current_week")) || null,
    startWeek: num(pick(league, "start_week")) || null,
    endWeek: num(pick(league, "end_week")) || null,
    numTeams: num(pick(league, "num_teams")) || null,
    startDate: str(pick(league, "start_date")),
    endDate: str(pick(league, "end_date")),
    tradeEndDate: str(pick(settings, "trade_end_date")),
    playoffStartWeek: num(pick(settings, "playoff_start_week")) || null,
    currentDate: str(pick(league, "current_date")),
  };
}

/** Yahoo's combined made/attempted stats, which arrive as "108/243". */
const SHOOTING_PAIRS: Record<string, [string, string]> = {
  "9004003": ["_FGM", "_FGA"],
  "9007006": ["_FTM", "_FTA"],
};

/** Read a `stats` list into numbers by stat id, splitting FGM/A and FTM/A into makes and
 *  attempts so percentages can be pooled. Returns undefined when every value is a dash,
 *  which is how Yahoo shows a day without a game, or a game not yet started. */
export function parseStats(entries: Record<string, unknown>[]): Record<string, number> | undefined {
  const values: Record<string, number> = {};
  let anyNumber = false;

  for (const stat of entries) {
    const statId = str(stat["stat_id"]);
    if (!statId) continue;
    const raw = str(stat["value"]).trim();
    if (raw === "" || raw === "-" || raw === "-/-") continue;
    anyNumber = true;

    const pair = SHOOTING_PAIRS[statId];
    const split = /^(\d+)\/(\d+)$/.exec(raw);
    if (pair && split) {
      values[pair[0]] = Number(split[1]);
      values[pair[1]] = Number(split[2]);
    } else {
      values[statId] = num(raw);
    }
  }

  return anyNumber ? values : undefined;
}

function parseTeamStats(team: Record<string, unknown>): Record<string, number> | undefined {
  return parseStats(unwrap(pick(team, "team_stats", "stats"), "stat"));
}

function parseTeam(team: Record<string, unknown>): YahooTeam {
  return {
    teamKey: str(team["team_key"]),
    teamId: str(team["team_id"]),
    name: str(team["name"]),
    stats: parseTeamStats(team),
  };
}

export async function fetchMatchup(teamKey: string, week?: number): Promise<Matchup> {
  const suffix = week ? `;weeks=${week}` : "";
  const data = await get(`/team/${teamKey}/matchups${suffix}`);
  const matchups = unwrap(pick(data, "fantasy_content", "team", "matchups"), "matchup");

  const chosen = week
    ? matchups.find((entry) => num(entry["week"]) === week) ?? matchups[0]
    : matchups.find((entry) => str(entry["status"]) !== "postevent") ?? matchups[0];

  if (!chosen) throw new YahooShapeError(`no matchup found for ${teamKey}`);

  const teams = unwrap(pick(chosen, "teams"), "team").map(parseTeam);
  return {
    week: num(chosen["week"]),
    weekStart: str(chosen["week_start"]),
    weekEnd: str(chosen["week_end"]),
    teams,
  };
}

function parsePlayer(player: Record<string, unknown>): YahooPlayer {
  const eligible = asArray(pick(player, "eligible_positions"))
    .map((entry) => (typeof entry === "string" ? entry : str(pick(entry, "position"))))
    .filter(Boolean);

  const stats = parseStats(unwrap(pick(player, "player_stats", "stats"), "stat"));

  return {
    playerKey: str(player["player_key"]),
    playerId: str(player["player_id"]),
    name: str(pick(player, "name", "full")) || str(player["name"]),
    teamAbbr: (str(player["editorial_team_abbr"]) || "").toUpperCase(),
    selectedPosition: str(pick(player, "selected_position", "position")),
    eligiblePositions: eligible,
    status: str(player["status"]),
    stats,
  };
}

/** A team's roster as it stands on `date`, with each player's line for that day (Yahoo
 *  returns today's roster for future dates). The line includes games in progress, which
 *  the feed never has. */
export async function fetchRoster(teamKey: string, date: string): Promise<YahooPlayer[]> {
  const data = await get(`/team/${teamKey}/roster;date=${date}/players/stats;type=date;date=${date}`);
  const players = unwrap(pick(data, "fantasy_content", "team", "roster", "players"), "player");
  return players.map(parsePlayer);
}

/** Roster plus each player's banked totals for the week — one call instead of one per day. */
export async function fetchRosterWithWeekStats(
  teamKey: string,
  week: number,
): Promise<YahooPlayer[]> {
  const data = await get(`/team/${teamKey}/roster/players;out=stats;type=week;week=${week}`);
  const players = unwrap(pick(data, "fantasy_content", "team", "roster", "players"), "player");
  return players.map(parsePlayer);
}

/** The signed-in user's teams for this game, so we know which team is theirs. */
export async function fetchUserTeams(gameKey: string): Promise<YahooTeam[]> {
  const data = await get(`/users;use_login=1/teams;game_keys=${gameKey}`);
  const users = unwrap(pick(data, "fantasy_content", "users"), "user");
  return unwrap(pick(users[0], "teams"), "team").map(parseTeam);
}

/** Every team's current roster in one call — the trade insights compare the whole league. */
export async function fetchLeagueRosters(leagueKey: string): Promise<LeagueRoster[]> {
  const data = await get(`/league/${leagueKey}/teams/roster`);
  const teams = unwrap(pick(data, "fantasy_content", "league", "teams"), "team");
  return teams.map((team) => {
    const managers = unwrap(pick(team, "managers"), "manager");
    const players = unwrap(pick(team, "roster", "players"), "player");
    return {
      teamKey: str(team["team_key"]),
      teamId: str(team["team_id"]),
      name: str(team["name"]),
      manager: str(managers[0]?.["nickname"]),
      players: players.map(parsePlayer),
    };
  });
}

export async function fetchFreeAgents(leagueKey: string, count = 50): Promise<YahooPlayer[]> {
  const data = await get(`/league/${leagueKey}/players;status=A;sort=AR;count=${count}`);
  const players = unwrap(pick(data, "fantasy_content", "league", "players"), "player");
  return players.map(parsePlayer);
}

/** League and team ids as they appear in the page URL: /nba/{leagueId}[/{teamId}]. */
export function parsePageContext(pathname: string): { leagueId: string; teamId: string | null } {
  const parts = pathname.split("/").filter(Boolean);
  const nbaIndex = parts.findIndex((part) => part.toLowerCase() === "nba");
  const leagueId = nbaIndex >= 0 ? parts[nbaIndex + 1] ?? "" : "";
  const maybeTeam = nbaIndex >= 0 ? parts[nbaIndex + 2] ?? "" : "";
  return {
    leagueId: /^\d+$/.test(leagueId) ? leagueId : "",
    teamId: /^\d+$/.test(maybeTeam) ? maybeTeam : null,
  };
}
