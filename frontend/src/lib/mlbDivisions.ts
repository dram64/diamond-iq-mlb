/**
 * Static lookup: MLB division integer ID → display metadata.
 *
 * Source: official MLB Stats API division IDs (the integers returned in
 * the `division.id` field on /standings responses). These have been
 * stable for decades; expansion / realignment would require an entry
 * here, but the last MLB realignment was 2013.
 *
 * Display order (`sortKey`) is the canonical "AL East / Central / West,
 * NL East / Central / West" sequence — the order most baseball fans
 * scan when reading the standings page.
 */

export type League = 'AL' | 'NL';

export interface MlbDivision {
  id: number;
  abbr: string;
  name: string;
  league: League;
  /** Stable display order across all 6 divisions, 0..5. */
  sortKey: number;
}

export const MLB_DIVISIONS: readonly MlbDivision[] = [
  { id: 201, abbr: 'AL East', name: 'American League East', league: 'AL', sortKey: 0 },
  { id: 202, abbr: 'AL Central', name: 'American League Central', league: 'AL', sortKey: 1 },
  { id: 200, abbr: 'AL West', name: 'American League West', league: 'AL', sortKey: 2 },
  { id: 204, abbr: 'NL East', name: 'National League East', league: 'NL', sortKey: 3 },
  { id: 205, abbr: 'NL Central', name: 'National League Central', league: 'NL', sortKey: 4 },
  { id: 203, abbr: 'NL West', name: 'National League West', league: 'NL', sortKey: 5 },
];

const byId: ReadonlyMap<number, MlbDivision> = new Map(MLB_DIVISIONS.map((d) => [d.id, d]));

/** Look up a division by id. Returns undefined for unknown ids. */
export function getMlbDivision(id: number): MlbDivision | undefined {
  return byId.get(id);
}

/**
 * Group teams by division id and return them in canonical display order.
 * Teams within each division come back in the order supplied — caller
 * is expected to have sorted by division_rank ascending if that matters.
 */
export function groupByDivision<T extends { division_id: number }>(
  teams: readonly T[],
): { division: MlbDivision; teams: T[] }[] {
  const buckets = new Map<number, T[]>();
  for (const team of teams) {
    const arr = buckets.get(team.division_id);
    if (arr) arr.push(team);
    else buckets.set(team.division_id, [team]);
  }
  return MLB_DIVISIONS.map((d) => ({ division: d, teams: buckets.get(d.id) ?? [] })).filter(
    (g) => g.teams.length > 0,
  );
}
