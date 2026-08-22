# Shams Draft Assistant (Chrome extension)

Punt-aware 9-cat recommendations and category scarcity in a side panel next to
your Yahoo fantasy basketball draft.

No build step. The files here load as-is, which is deliberate: on draft day the
last thing you want between you and a working tool is a broken bundler.

## Install

1. Start the backend:

   ```bash
   ./scripts/dev.sh          # or: cd backend && uvicorn app.main:app --port 8000
   curl localhost:8000/api/draft/health     # {"status":"ready",...}
   ```

2. Open `chrome://extensions`, enable **Developer mode**, click
   **Load unpacked**, and select this `extension/` directory.

3. Copy the extension id Chrome assigns and add it to `.env` so CORS allows it:

   ```
   DRAFT_EXTENSION_ID=abcdefghijklmnopabcdefghijklmnop
   ```

   With `DEBUG=true` any extension origin is allowed, so you can skip this while
   developing.

4. Open your draft room. Click the Shams toolbar icon to open the side panel.

## How it works

```
Yahoo draft room (React + Redux)
        │  main-world.js       world: MAIN, document_start
        │                      locates the Redux store on the fiber tree,
        │                      store.subscribe() → push on every change
        ▼  CustomEvent
   content.js                  world: ISOLATED — the only bridge to chrome.*
        ▼  chrome.runtime.sendMessage
  background.js                POSTs the whole state to the backend
        ▼  fetch
  POST /api/draft/state        recomputes from scratch, returns the board
        ▼
  panel/                       renders it
```

Two properties matter:

- **Idempotent.** Every push carries the complete state, so dropped, duplicated
  or out-of-order messages are harmless, and a mid-draft refresh is a non-event.
- **Read-only.** Nothing is ever written to the Yahoo page. You read the
  recommendation and make the pick yourself.

The page's own CSP blocks it from reaching localhost, which is why the network
call lives in the service worker rather than in the injected script.

## When it breaks

The fragile part is `extract()` in `main-world.js` — it maps Yahoo's Redux
slices onto the payload. If Yahoo refactors the store, the panel shows
**"Could not find Yahoo's draft store"** rather than quietly serving a stale
board.

To fix: join an instant mock draft, open DevTools, and re-run the recon in
`docs/draft-room-recon.md`. The store is normally ~31 fiber nodes from the root
at `memoizedProps.store`.

## Collecting fixtures

Run the backend with capture on, then play a mock draft:

```bash
SHAMS_DRAFT_CAPTURE_DIR=~/.shams/draft-captures uvicorn app.main:app --port 8000
```

Every payload lands in that directory as JSON, giving you real snapshots to
develop and test against in July when no draft is running.

## Before draft day

- Run at least one full mock draft end to end.
- Confirm `/api/draft/health` responds *before* the draft, not at pick 1.
- Check the panel's footer shows a compute time; if it's climbing above a few
  hundred ms, the shortlist size in `tools/draft/recommender.py` is the knob.
