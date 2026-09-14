/**
 * Isolated-world relay.
 *
 * The MAIN-world script can see React but cannot touch chrome.*; this script is
 * the reverse. It does nothing but forward, which keeps the extension's
 * privileged surface as small as possible.
 */

(() => {
  "use strict";

  const forward = (type, detail) => {
    try {
      chrome.runtime.sendMessage({ type, ...detail });
    } catch (err) {
      // The service worker restarts on its own schedule; a dropped message is
      // harmless because the next push carries the complete state anyway.
    }
  };

  window.addEventListener("shams:draft-state", (event) => {
    const { reason, payload } = event.detail || {};
    forward("DRAFT_STATE", { reason, payload });
  });

  window.addEventListener("shams:draft-status", (event) => {
    forward("DRAFT_STATUS", { status: event.detail });
  });

  // Tell the worker the draft room is open, so the panel can stop saying
  // "waiting for a draft" the moment the tab loads.
  forward("DRAFT_ROOM_OPEN", { url: location.href });
})();
