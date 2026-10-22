// Joining a Yahoo roster row to NBA stats.
//
// The Yahoo id index only covers players a past waiver or ranking run touched, so most
// rosters miss it entirely. Python falls back to matching on name
// (player_fetcher.player_id_lookup); this is the same fallback, normalizing names the
// same way tools/utils/player_index.normalize_player_name does.

import type { PlayerIndexFile } from "../feed/types";

export function normalizePlayerName(name: string): string {
  return name
    .normalize("NFKD")
    // Strip the combining marks NFKD split off, which is what Python's
    // encode("ascii", "ignore") does to accented characters.
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^\x20-\x7e]/g, "")
    .trim()
    .toLowerCase();
}

export function resolveNbaId(
  index: PlayerIndexFile,
  yahooPlayerId: string,
  playerName: string,
): string | null {
  const byId = index.yahoo_to_nba[yahooPlayerId];
  if (byId) return byId;

  const byName = index.name_to_nba?.[normalizePlayerName(playerName)];
  return byName ?? null;
}
