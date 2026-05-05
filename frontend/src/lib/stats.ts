const RATE_STATS_PASS_THROUGH = new Set(['avg', 'obp', 'slg', 'ops', 'era', 'whip']);

const COUNTING_STATS = new Set(['hr', 'rbi', 'k', 'wins', 'saves', 'home_runs', 'strikeouts']);

/**
 * URL stat token → DynamoDB storage attribute name.
 *
 * Mirrors the backend's `_LEADER_STATS[group][stat].field` mapping for stats
 * where the URL token differs from the storage column. Tokens not in this
 * map (e.g. avg, era, whip, woba, fip, ops_plus) read back from the same
 * attribute name as the URL token.
 *
 * Single-source-of-truth note: the canonical mapping lives in
 * functions/api_players/routes/leaders.py. Frontend keeps a parallel copy
 * here so secondary-stat columns can read row[storageField] without an
 * extra round-trip. If the backend adds a new token-with-rename, this
 * map needs to be updated in lockstep — documented in ADR 012 .
 */
export const STAT_STORAGE_FIELD: Readonly<Record<string, string>> = {
  hr: 'home_runs',
  k: 'strikeouts',
};

/** Resolve the DynamoDB attribute name a leader-row value lives under. */
export function statStorageField(token: string): string {
  return STAT_STORAGE_FIELD[token] ?? token;
}

/**
 * Stats where a LOWER value is better. Mirrors the backend
 * _LEADER_STATS direction config for symmetry. Used by
 * compareStatBetter to flip the winner test and by the side-by-side
 * bar renderer to invert the bar fill so visually-longer = better.
 */
const ASCENDING_STATS = new Set(['era', 'whip', 'fip']);

/** Coerce a stat value (string from API or number from Decimal) to a finite
 *  number, returning null if it can't be parsed. */
function toNumber(value: number | string | null | undefined): number | null {
  if (value === null || value === undefined) return null;
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  if (typeof value === 'string') {
    const s = value.trim();
    if (!s) return null;
    const n = Number.parseFloat(s);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

/**
 * Decide which of two values is "better" for a given stat. Direction-aware:
 * for ascending stats (ERA/WHIP/FIP) lower wins; for everything else
 * higher wins. Returns null if either value is missing/unparseable so the
 * caller can render neutral styling rather than a misleading winner.
 */
export function compareStatBetter(
  stat: string,
  a: number | string | null | undefined,
  b: number | string | null | undefined,
): 'a' | 'b' | 'tie' | null {
  const na = toNumber(a);
  const nb = toNumber(b);
  if (na === null || nb === null) return null;
  if (na === nb) return 'tie';
  const ascending = ASCENDING_STATS.has(stat);
  if (ascending) return na < nb ? 'a' : 'b';
  return na > nb ? 'a' : 'b';
}

export function isAscendingStat(stat: string): boolean {
  return ASCENDING_STATS.has(stat);
}

export function parseStatNumber(value: number | string | null | undefined): number | null {
  return toNumber(value);
}

/** Strip a leading "0" before a decimal point so 0.399 renders as ".399". */
function strip_leading_zero(s: string): string {
  if (s.startsWith('0.')) return s.slice(1);
  if (s.startsWith('-0.')) return '-' + s.slice(2);
  return s;
}

export function formatStat(stat: string, value: number | string | null | undefined): string {
  if (value === null || value === undefined) return '—';

  // Strings from the API are already display-formatted (".300", "3.50").
  // Pass through unchanged; no parse / re-render churn.
  if (typeof value === 'string') {
    return value || '—';
  }

  if (Number.isNaN(value)) return '—';

  // 5D-computed rate stats — Decimal-from-DynamoDB → number → 3dp .399 form.
  if (stat === 'woba') return strip_leading_zero(value.toFixed(3));

  // FIP renders to 2 decimals like ERA/WHIP for visual symmetry on the card.
  if (stat === 'fip') return value.toFixed(2);

  // OPS+ is a whole-number index where 100 = league average.
  if (stat === 'ops_plus') return Math.round(value).toString();

  // Counting stats — integer.
  if (COUNTING_STATS.has(stat)) return Math.round(value).toString();

  // Numeric form of a rate stat that the API would normally have stringified.
  // Round to 3 decimals and strip leading zero for display consistency.
  if (RATE_STATS_PASS_THROUGH.has(stat)) {
    return strip_leading_zero(value.toFixed(3));
  }

  // Fallback — render as-is.
  return value.toString();
}
