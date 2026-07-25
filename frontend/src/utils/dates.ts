/**
 * Local-timezone-safe helpers for date-only (YYYY-MM-DD) values.
 *
 * `new Date("YYYY-MM-DD")` parses as UTC midnight, and `Date.toISOString()`
 * serializes in UTC. Mixing those with local-time comparisons (e.g.
 * `new Date()`, `setHours(0,0,0,0)`) shifts the calendar date by a day for any
 * viewer west of UTC once it's evening locally. These helpers keep every
 * date-only value anchored to the viewer's local calendar day.
 */

/** Format a Date as a local-calendar `YYYY-MM-DD` string (no UTC shift). */
export function formatLocalDate(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

/** Parse a `YYYY-MM-DD` string as local midnight (not UTC midnight). */
export function parseLocalDate(value: string): Date {
  // Appending a time component makes the parse local rather than UTC.
  return new Date(`${value}T00:00:00`);
}

/** Today's local calendar date as `YYYY-MM-DD`. */
export function todayLocalISO(): string {
  return formatLocalDate(new Date());
}
