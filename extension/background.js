/**
 * Service worker: the only component that talks to the Shams backend.
 *
 * The contract is deliberately idempotent — every push carries the complete
 * draft state and the backend recomputes from scratch. Dropped, duplicated or
 * out-of-order messages are therefore all harmless, which is what makes a
 * mid-draft refresh or reconnect a non-event.
 */

const DEFAULT_BACKEND = "http://localhost:8000";
/** Players the user marked drafted by hand when the adapter missed them. */
let manualPicks = [];
/** Never let two analyses overlap; the newest state always wins. */
let inFlight = false;
let pending = null;

/** Last board and status, so a panel opened mid-draft renders immediately. */
let latest = {
  board: null,
  status: { status: "idle", message: "Open your Yahoo draft room to begin." },
  error: null,
  updatedAt: null,
};

const backendUrl = async () => {
  try {
    const stored = await chrome.storage.local.get("backendUrl");
    return stored.backendUrl || DEFAULT_BACKEND;
  } catch (err) {
    return DEFAULT_BACKEND;
  }
};

const broadcast = () => {
  // No receiver is a normal state (the panel may be closed), so swallow.
  chrome.runtime.sendMessage({ type: "BOARD_UPDATED", ...latest }).catch(() => {});
};

const setStatus = (status, message, extra = {}) => {
  latest.status = { status, message, ...extra };
  broadcast();
};

const analyze = async (payload) => {
  const base = await backendUrl();
  const response = await fetch(`${base}/api/draft/state`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(`Backend returned ${response.status} ${response.statusText}`);
  }
  return response.json();
};

/** The newest raw snapshot, kept unmerged so manual picks apply cleanly. */
let lastPayload = null;

const run = async (payload) => {
  lastPayload = payload;

  if (inFlight) {
    // Keep only the newest; older snapshots are strictly stale.
    pending = payload;
    return;
  }

  inFlight = true;
  try {
    // Merged at send time so a manual correction survives later snapshots.
    const board = await analyze({ ...payload, manualPicks });
    latest.board = board;
    latest.error = null;
    latest.updatedAt = new Date().toISOString();
    latest.status = {
      status: "live",
      message: `Pick ${board.current_pick + 1}`,
    };
    broadcast();
  } catch (err) {
    latest.error = String((err && err.message) || err);
    latest.status = {
      status: "backend-unreachable",
      message:
        "Cannot reach the Shams backend. Start it with ./scripts/dev.sh before the draft.",
    };
    broadcast();
  } finally {
    inFlight = false;
    if (pending) {
      const next = pending;
      pending = null;
      run(next);
    }
  }
};

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  switch (message?.type) {
    case "DRAFT_STATE":
      run(message.payload);
      break;

    case "DRAFT_STATUS": {
      const { status, message: detail } = message.status || {};
      if (status === "connected") {
        setStatus("connected", "Reading the draft room.");
      } else if (status) {
        setStatus(status, detail || "The draft room adapter reported a problem.");
      }
      break;
    }

    case "DRAFT_ROOM_OPEN":
      setStatus("waiting", "Draft room open, waiting for the store.");
      break;

    case "GET_BOARD":
      sendResponse(latest);
      return true;

    case "SET_BACKEND_URL":
      chrome.storage.local.set({ backendUrl: message.url });
      break;

    case "MARK_DRAFTED":
      if (message.playerId && !manualPicks.includes(message.playerId)) {
        manualPicks.push(message.playerId);
        if (lastPayload) run(lastPayload);
      }
      break;

    case "CLEAR_MANUAL_PICKS":
      manualPicks = [];
      if (lastPayload) run(lastPayload);
      break;

    default:
      break;
  }
  return false;
});

// Clicking the toolbar icon opens the panel next to the draft room.
chrome.runtime.onInstalled.addListener(() => {
  chrome.sidePanel
    .setPanelBehavior({ openPanelOnActionClick: true })
    .catch(() => {});
});
