// Who starts on a given day when more players have a game than there are active slots.
//
// rosterOptimizer.ts (a port of the Python) maximizes how many players start, which is the
// right question for one matchup week. Played out over a season the question is who should
// sit when the slots run out, and that needs value. Fitting players to slots is a bipartite
// matching; taking players best-first and keeping each one that can still be fitted —
// shuffling earlier starters between slots when that makes room — is the greedy algorithm
// on a transversal matroid, which is optimal for total value. Everyone who can be fitted
// still starts, so no slot is left empty to make a point.

import { INACTIVE_POSITIONS, canFillSlot } from "./rosterOptimizer";

export interface LineupCandidate {
  key: string;
  eligiblePositions: string[];
  value: number;
}

/** Specific slots first, then G/F, then Util, so a guard who could fill PG is credited to
 *  PG rather than soaking up a Util slot someone else needed. */
function slotSpecificity(slot: string): number {
  if (slot === "Util") return 3;
  if (slot === "G" || slot === "F") return 2;
  return 1;
}

/** Candidate key -> slot for every starter; anyone missing from the map sits. */
export function bestLineup(candidates: LineupCandidate[], rosterPositions: string[]): Map<string, string> {
  const slots = rosterPositions.filter((position) => !INACTIVE_POSITIONS.has(position));
  const ordered = candidates
    .slice()
    .sort((a, b) => b.value - a.value || a.key.localeCompare(b.key));

  const fits = ordered.map((candidate) =>
    slots
      .map((slot, index) => ({ slot, index }))
      .filter(({ slot }) => canFillSlot(candidate.eligiblePositions, slot))
      .sort((a, b) => slotSpecificity(a.slot) - slotSpecificity(b.slot) || a.index - b.index)
      .map(({ index }) => index),
  );

  /** Index into `ordered` of the player in each slot. */
  const holder: (number | null)[] = slots.map(() => null);

  // Augmenting path: put `player` in a free slot, or in an occupied one whose holder can
  // move somewhere else.
  const place = (player: number, visited: boolean[]): boolean => {
    for (const slot of fits[player] ?? []) {
      if (visited[slot]) continue;
      visited[slot] = true;
      const current = holder[slot] ?? null;
      if (current === null || place(current, visited)) {
        holder[slot] = player;
        return true;
      }
    }
    return false;
  };

  for (let player = 0; player < ordered.length; player += 1) {
    place(player, slots.map(() => false));
  }

  const lineup = new Map<string, string>();
  holder.forEach((player, slotIndex) => {
    if (player === null) return;
    const candidate = ordered[player];
    const slot = slots[slotIndex];
    if (candidate && slot) lineup.set(candidate.key, slot);
  });
  return lineup;
}
