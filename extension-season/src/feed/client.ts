// Content-script side: ask the background script for the feed rather than fetching it here,
// so one cache serves every tab.

import type { Feed, FeedStatus } from "./types";

function send<T>(message: unknown): Promise<T> {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage(message, (response) => {
      if (chrome.runtime.lastError) {
        reject(new Error(chrome.runtime.lastError.message));
        return;
      }
      if (!response?.ok) {
        reject(new Error(response?.error ?? "no response from the Shams background script"));
        return;
      }
      resolve(response as T);
    });
  });
}

export async function getFeed(force = false): Promise<Feed> {
  const response = await send<{ feed: Feed }>({ type: "GET_FEED", force });
  return response.feed;
}

export async function getFeedStatus(): Promise<FeedStatus> {
  const response = await send<{ status: FeedStatus }>({ type: "GET_FEED_STATUS" });
  return response.status;
}
