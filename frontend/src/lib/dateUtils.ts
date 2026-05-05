/**
 * Date helpers, stdlib-only. All values are UTC.
 *
 * The frontend's "today" is the same UTC date the backend partitions by,
 * so callers can pass these strings straight into `fetchScoreboard(date)`.
 */

function pad2(n: number): string {
  return n.toString().padStart(2, '0');
}

function toUtcIsoDate(d: Date): string {
  return `${d.getUTCFullYear()}-${pad2(d.getUTCMonth() + 1)}-${pad2(d.getUTCDate())}`;
}

/** YYYY-MM-DD for today's UTC date. */
export function todayUtcDate(now: Date = new Date()): string {
  return toUtcIsoDate(now);
}

/** YYYY-MM-DD for the UTC date one day before today. */
export function yesterdayUtcDate(now: Date = new Date()): string {
  const ms = now.getTime() - 24 * 60 * 60 * 1000;
  return toUtcIsoDate(new Date(ms));
}
