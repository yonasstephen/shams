// Port of tools/matchup/roster_optimizer.py — greedy slot assignment that maximizes the
// number of players who actually start on a given day.

export const INACTIVE_POSITIONS = new Set(["BN", "IL", "IL+", "DNP", ""]);

export interface OptimizablePlayer {
  playerKey: string;
  eligiblePositions: string[];
}

export function canFillSlot(positions: string[], slot: string): boolean {
  if (slot === "Util") return true;
  if (slot === "G") return positions.includes("PG") || positions.includes("SG");
  if (slot === "F") return positions.includes("SF") || positions.includes("PF");
  return positions.includes(slot);
}

function slotPriority(positions: string[], slot: string): number {
  if (positions.includes(slot)) return 1;
  if (slot === "G" && (positions.includes("PG") || positions.includes("SG"))) return 2;
  if (slot === "F" && (positions.includes("SF") || positions.includes("PF"))) return 2;
  if (slot === "Util") return 3;
  return 999;
}

export function optimizeRosterPositions(
  players: OptimizablePlayer[],
  leagueRosterPositions: string[],
  playersWithGames: Set<string>,
  playerRanks: Record<string, number> = {},
): Record<string, string> {
  const activeSlots = leagueRosterPositions.filter((position) => !INACTIVE_POSITIONS.has(position));
  const available = new Map<number, string>(activeSlots.map((slot, index) => [index, slot]));
  const assignments: Record<string, string> = {};

  const queue = players
    .filter((player) => player.playerKey && playersWithGames.has(player.playerKey))
    .filter((player) => player.eligiblePositions.length > 0)
    .map((player) => ({
      playerKey: player.playerKey,
      eligiblePositions: player.eligiblePositions,
      flexibility: player.eligiblePositions.length,
      rank: playerRanks[player.playerKey] ?? 9999,
    }))
    // Least flexible first, then by rank, then by key — identical ordering to the Python,
    // which matters because a different order produces a different valid assignment.
    .sort((a, b) =>
      a.flexibility - b.flexibility ||
      a.rank - b.rank ||
      a.playerKey.localeCompare(b.playerKey),
    );

  for (const player of queue) {
    let bestSlot: number | null = null;
    let bestPriority = 999;

    for (const [index, slot] of available) {
      if (!canFillSlot(player.eligiblePositions, slot)) continue;
      const priority = slotPriority(player.eligiblePositions, slot);
      if (priority < bestPriority) {
        bestPriority = priority;
        bestSlot = index;
      }
    }

    if (bestSlot !== null) {
      assignments[player.playerKey] = available.get(bestSlot) as string;
      available.delete(bestSlot);
    } else {
      assignments[player.playerKey] = "BN";
    }
  }

  for (const player of players) {
    if (player.playerKey && !(player.playerKey in assignments)) {
      assignments[player.playerKey] = "BN";
    }
  }

  return assignments;
}

export function getActivePositions(assignments: Record<string, string>): Set<string> {
  return new Set(
    Object.entries(assignments)
      .filter(([, position]) => !INACTIVE_POSITIONS.has(position))
      .map(([playerKey]) => playerKey),
  );
}

export function isActivePosition(position: string): boolean {
  return !INACTIVE_POSITIONS.has(position);
}
