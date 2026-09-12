/**
 * Runs in the page's own JavaScript world, at document_start.
 *
 * Yahoo's draft client is a Redux app. Rather than scraping rendered DOM — which
 * loses everything on a refresh and breaks on any re-skin — this locates the
 * store object hanging off the React fiber tree and subscribes to it. See
 * docs/draft-room-recon.md.
 *
 * This file reads and relays. It holds no credentials and makes no decisions,
 * because the page shares this world and can tamper with anything here.
 */

(() => {
  "use strict";

  const EVENT = "shams:draft-state";
  const STATUS_EVENT = "shams:draft-status";
  /** Redux fires on every action; coalesce bursts into one push. */
  const DEBOUNCE_MS = 200;
  /** Resend even without changes, so a dropped message self-heals. */
  const HEARTBEAT_MS = 10000;
  /** How often to look for the store before React has mounted. */
  const LOCATE_INTERVAL_MS = 300;
  const LOCATE_TIMEOUT_MS = 60000;

  let store = null;
  let debounceTimer = null;
  let lastPushAt = 0;

  const emitStatus = (status, detail) => {
    window.dispatchEvent(
      new CustomEvent(STATUS_EVENT, { detail: { status, ...detail } })
    );
  };

  /** Whether an object quacks like a Redux store. */
  const isStore = (candidate) =>
    candidate &&
    typeof candidate === "object" &&
    typeof candidate.getState === "function" &&
    typeof candidate.dispatch === "function" &&
    typeof candidate.subscribe === "function";

  /**
   * Walk up from any mounted element to the fiber root, then scan the tree for
   * the store. In practice it sits ~31 nodes in, on memoizedProps.store.
   */
  const locateStore = () => {
    const anchor = document.querySelector("#app *") || document.querySelector("#app");
    if (!anchor) return null;

    const fiberKey = Object.keys(anchor).find((key) => key.startsWith("__reactFiber$"));
    if (!fiberKey) return null;

    let root = anchor[fiberKey];
    while (root && root.return) root = root.return;
    if (!root) return null;

    let found = null;
    let visited = 0;
    const walk = (fiber) => {
      if (!fiber || found || visited > 20000) return;
      visited += 1;
      for (const bag of ["memoizedProps", "memoizedState"]) {
        const container = fiber[bag];
        if (!container || typeof container !== "object") continue;
        if (isStore(container)) {
          found = container;
          return;
        }
        let keys;
        try {
          keys = Object.keys(container);
        } catch (err) {
          continue;
        }
        for (const key of keys) {
          let value;
          try {
            value = container[key];
          } catch (err) {
            continue;
          }
          if (isStore(value)) {
            found = value;
            return;
          }
        }
      }
      walk(fiber.child);
      walk(fiber.sibling);
    };
    walk(root);
    return found;
  };

  /** Fields we forward per player. The full objects are far larger than needed. */
  const PLAYER_FIELDS = [
    "id",
    "fname",
    "lname",
    "pos",
    "display_pos",
    "primary_pos",
    "team_abbr",
    "inj",
    "inj_note",
    "o_rank",
    "psr_rank",
    "auction-value",
    "average-pick",
    "preseason-average-pick",
    "percent-drafted",
  ];

  const trimPlayer = (player) => {
    const out = {};
    for (const field of PLAYER_FIELDS) out[field] = player[field];
    // Stat blobs are keyed by Yahoo stat id; forward them intact.
    out.projected_stats = player.projected_stats;
    out.season_stats = player.season_stats;
    out.average_stats = player.average_stats;
    return out;
  };

  /**
   * Map the store's slices onto the payload the backend parses.
   * This is the adapter — the one part that rots when Yahoo refactors.
   */
  const extract = (state) => {
    const players = Array.isArray(state.players?.all)
      ? state.players.all
      : Object.values(state.players?.byId || {});

    // `order` is authoritative when populated, but it can be an empty array
    // while byId holds picks — and `[] || fallback` yields the empty array,
    // which would silently report a draft with zero picks. Check length.
    //
    // Its entries are the pick objects themselves, not keys into byId, which is
    // keyed by playerId — so indexing one with the other stringifies to
    // "[object Object]" and every lookup misses. Both shapes have now been seen,
    // so accept either rather than assuming one.
    const picksById = state.draftPicks?.byId || {};
    const pickOrder = state.draftPicks?.order;
    const pickKeys = pickOrder && pickOrder.length ? pickOrder : Object.keys(picksById);
    const picks = pickKeys.map((entry) =>
      entry && typeof entry === "object" ? entry : picksById[entry]
    );

    // Resolving none of them is this adapter's most likely silent failure: the
    // board still computes, it just computes round one forever.
    if (pickKeys.length && !picks.some(Boolean)) {
      emitStatus("picks-unmapped", { count: pickKeys.length });
    }

    const teams = {};
    for (const [id, team] of Object.entries(state.league?.teams || {})) {
      teams[id] = { id: team.id, teamname: team.teamname };
    }

    return {
      capturedAt: new Date().toISOString(),
      draft: state.draft,
      context: {
        leagueId: state.context?.leagueId,
        managerId: state.context?.managerId,
        isPremium: state.context?.isPremium,
        sportCode: state.context?.sportCode,
      },
      countdown: state.countdown,
      draftOrder: {
        currentPick: state.draftOrder?.currentPick,
        currentTeam: state.draftOrder?.currentTeam,
        order: state.draftOrder?.order,
      },
      picks: picks.filter(Boolean),
      queue: state.queue,
      teams,
      players: players.filter(Boolean).map(trimPlayer),
      // The nested `settings.settings` holds roster_positions and
      // stat_categories; the outer object holds league_id, num_teams, pickTime.
      settings: state.settings,
    };
  };

  const push = (reason) => {
    if (!store) return;
    let payload;
    try {
      payload = extract(store.getState());
    } catch (err) {
      emitStatus("extract-failed", { message: String(err && err.message) });
      return;
    }
    lastPushAt = Date.now();
    window.dispatchEvent(new CustomEvent(EVENT, { detail: { reason, payload } }));
  };

  const schedulePush = (reason) => {
    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      debounceTimer = null;
      push(reason);
    }, DEBOUNCE_MS);
  };

  const attach = (located) => {
    store = located;
    emitStatus("connected", { url: location.href });
    try {
      store.subscribe(() => schedulePush("store-change"));
    } catch (err) {
      emitStatus("subscribe-failed", { message: String(err && err.message) });
    }
    push("initial");

    // A heartbeat covers the case where a message is lost or the subscription
    // silently stops firing after a Yahoo refactor.
    setInterval(() => {
      if (Date.now() - lastPushAt >= HEARTBEAT_MS) push("heartbeat");
    }, HEARTBEAT_MS);
  };

  const startedAt = Date.now();
  const locateTimer = setInterval(() => {
    const located = locateStore();
    if (located) {
      clearInterval(locateTimer);
      attach(located);
      return;
    }
    if (Date.now() - startedAt > LOCATE_TIMEOUT_MS) {
      clearInterval(locateTimer);
      // Loudly, not silently: a quiet failure here means a draft with no help.
      emitStatus("store-not-found", {
        message:
          "Could not find Yahoo's draft store. The page structure likely changed — " +
          "re-run recon (docs/draft-room-recon.md) and update the adapter.",
      });
    }
  }, LOCATE_INTERVAL_MS);
})();
