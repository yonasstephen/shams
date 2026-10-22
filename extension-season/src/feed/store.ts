// Service-worker side of the feed: fetch, decompress, cache, hand out.
//
// The files are gzipped and GitHub serves them without Content-Encoding, so the browser
// does not unwrap them for us — DecompressionStream does.

import type { Feed, FeedMeta, FeedStatus } from "./types";
import { FEED_SCHEMA } from "./types";

const DEFAULT_BASE_URL = "https://raw.githubusercontent.com/yonasstephen/shams/feed";
const CACHE_KEY = "feed.cache";
const BASE_URL_KEY = "feed.baseUrl";
const RECHECK_AFTER_MS = 6 * 60 * 60 * 1000;

interface CachedFeed {
  baseUrl: string;
  fetchedAt: string;
  checkedAt: string;
  feed: Feed;
}

let inFlight: Promise<Feed> | null = null;

export async function getBaseUrl(): Promise<string> {
  const stored = await chrome.storage.local.get(BASE_URL_KEY);
  const value = stored[BASE_URL_KEY];
  return typeof value === "string" && value ? value.replace(/\/+$/, "") : DEFAULT_BASE_URL;
}

export async function setBaseUrl(url: string): Promise<void> {
  await chrome.storage.local.set({ [BASE_URL_KEY]: url.replace(/\/+$/, "") });
  await chrome.storage.local.remove(CACHE_KEY);
}

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { cache: "no-cache" });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText} for ${url}`);
  }
  if (!url.endsWith(".gz")) {
    return (await response.json()) as T;
  }
  if (!response.body) {
    throw new Error(`empty body for ${url}`);
  }
  const stream = response.body.pipeThrough(new DecompressionStream("gzip"));
  return JSON.parse(await new Response(stream).text()) as T;
}

async function readCache(): Promise<CachedFeed | null> {
  const stored = await chrome.storage.local.get(CACHE_KEY);
  const cached = stored[CACHE_KEY] as CachedFeed | undefined;
  return cached ?? null;
}

async function download(baseUrl: string): Promise<Feed> {
  const meta = await fetchJson<FeedMeta>(`${baseUrl}/meta.json`);
  if (meta.schema !== FEED_SCHEMA) {
    throw new Error(
      `feed schema ${meta.schema} but this build expects ${FEED_SCHEMA} — update the extension`,
    );
  }

  const [projections, players, playersPrev, schedule, index] = await Promise.all([
    fetchJson<Feed["projections"]>(`${baseUrl}/projections.json.gz`),
    fetchJson<Feed["players"]>(`${baseUrl}/players.json.gz`),
    fetchJson<Feed["playersPrev"]>(`${baseUrl}/players-prev.json.gz`),
    fetchJson<Feed["schedule"]>(`${baseUrl}/schedule.json.gz`),
    fetchJson<Feed["index"]>(`${baseUrl}/player-index.json.gz`),
  ]);

  return { meta, projections, players, playersPrev, schedule, index };
}

/** The feed, from cache when it is current, from the network when it is not. */
export async function loadFeed(options: { force?: boolean } = {}): Promise<Feed> {
  if (inFlight && !options.force) return inFlight;

  inFlight = (async () => {
    const baseUrl = await getBaseUrl();
    const cached = await readCache();
    const now = Date.now();

    if (cached && cached.baseUrl === baseUrl && !options.force) {
      const age = now - Date.parse(cached.checkedAt);
      if (age < RECHECK_AFTER_MS) return cached.feed;

      // Past the recheck window: meta.json is small, so ask it whether anything
      // actually changed before pulling a couple of hundred kilobytes again.
      try {
        const meta = await fetchJson<FeedMeta>(`${baseUrl}/meta.json`);
        if (meta.generated_at === cached.feed.meta.generated_at) {
          await chrome.storage.local.set({
            [CACHE_KEY]: { ...cached, checkedAt: new Date(now).toISOString() },
          });
          return cached.feed;
        }
      } catch {
        // Offline or the branch is briefly unavailable: stale data still projects.
        return cached.feed;
      }
    }

    const feed = await download(baseUrl);
    const entry: CachedFeed = {
      baseUrl,
      fetchedAt: new Date(now).toISOString(),
      checkedAt: new Date(now).toISOString(),
      feed,
    };
    await chrome.storage.local.set({ [CACHE_KEY]: entry });
    return feed;
  })();

  try {
    return await inFlight;
  } finally {
    inFlight = null;
  }
}

export async function feedStatus(): Promise<FeedStatus> {
  try {
    const cached = await readCache();
    if (!cached) return { state: "empty" };
    return {
      state: "ready",
      season: cached.feed.meta.season,
      generatedAt: cached.feed.meta.generated_at,
      fetchedAt: cached.fetchedAt,
    };
  } catch (error) {
    return { state: "error", error: String(error) };
  }
}
