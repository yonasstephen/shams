// Thin service worker: owns the feed cache, answers content scripts and the popup.
// No analysis happens here — the content scripts run the engine where the page is.

import { feedStatus, getBaseUrl, loadFeed, setBaseUrl } from "./feed/store";

type Request =
  | { type: "GET_FEED"; force?: boolean }
  | { type: "GET_FEED_STATUS" }
  | { type: "GET_BASE_URL" }
  | { type: "SET_BASE_URL"; url: string };

chrome.runtime.onMessage.addListener((message: Request, _sender, sendResponse) => {
  (async () => {
    switch (message.type) {
      case "GET_FEED": {
        const feed = await loadFeed({ force: message.force });
        sendResponse({ ok: true, feed });
        break;
      }
      case "GET_FEED_STATUS":
        sendResponse({ ok: true, status: await feedStatus() });
        break;
      case "GET_BASE_URL":
        sendResponse({ ok: true, url: await getBaseUrl() });
        break;
      case "SET_BASE_URL":
        await setBaseUrl(message.url);
        sendResponse({ ok: true });
        break;
      default:
        sendResponse({ ok: false, error: "unknown message" });
    }
  })().catch((error: unknown) => {
    sendResponse({ ok: false, error: error instanceof Error ? error.message : String(error) });
  });

  return true; // keep the channel open for the async reply
});
