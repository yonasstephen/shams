// Yahoo's `format=json_f` returns collections as arrays of single-key wrapper objects
// (`[{team: {...}}, …]`), while some deployments still hand back the older count-keyed
// object form. These helpers read both so a shape change degrades into an empty list
// rather than a thrown error halfway through rendering.

export function asArray(value: unknown): unknown[] {
  if (Array.isArray(value)) return value;
  if (value && typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>)
      .filter(([key]) => /^\d+$/.test(key))
      .sort((a, b) => Number(a[0]) - Number(b[0]));
    if (entries.length) return entries.map(([, item]) => item);
  }
  return [];
}

/** Unwrap `[{player: {...}}]` to `[{...}]`, tolerating already-flat entries. */
export function unwrap(value: unknown, key: string): Record<string, unknown>[] {
  return asArray(value)
    .map((item) => {
      if (!item || typeof item !== "object") return null;
      const record = item as Record<string, unknown>;
      const inner = record[key];
      if (inner && typeof inner === "object") return inner as Record<string, unknown>;
      return record;
    })
    .filter((item): item is Record<string, unknown> => item !== null);
}

export function str(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number") return String(value);
  return "";
}

export function num(value: unknown): number {
  if (typeof value === "number") return Number.isFinite(value) ? value : 0;
  if (typeof value === "string") {
    const cleaned = value.trim();
    if (cleaned === "" || cleaned === "-" || cleaned === "-/-") return 0;
    const parsed = Number(cleaned);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
}

export function pick(source: unknown, ...path: string[]): unknown {
  let current: unknown = source;
  for (const key of path) {
    if (!current || typeof current !== "object") return undefined;
    current = (current as Record<string, unknown>)[key];
  }
  return current;
}
