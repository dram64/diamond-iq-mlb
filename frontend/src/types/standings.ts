export interface StandingsRecordRaw {
  team_id: number;
  team_name: string;
  division_id: number;
  division_name?: string | null;
  league_id: number;
  league_name?: string | null;
  wins: number;
  losses: number;
  /** Pre-formatted by the API as ".643" — pass through. */
  pct: string;
  /** "-" for division leader, "1.5" for trailing teams. */
  games_back: string;
  wild_card_games_back?: string | null;
  /** "W3" / "L1" — empty / null at season start. */
  streak_code: string | null;
  last_ten_record?: string | null;
  home_record?: string | null;
  away_record?: string | null;
  run_differential: number;
  runs_scored?: number;
  runs_allowed?: number;
  /** API may return as string ("1") or number; coerced to number on parse. */
  division_rank: number | string;
  league_rank: number | string;
  games_played?: number;
  season?: number;
}

/** Coerced shape that the rest of the app sees — ranks are always numbers. */
export interface StandingsRecord extends Omit<StandingsRecordRaw, 'division_rank' | 'league_rank'> {
  division_rank: number;
  league_rank: number;
}

export interface StandingsData {
  season: number;
  teams: StandingsRecord[];
}

export interface StandingsMeta {
  season: number;
  timestamp: string;
  cache_max_age_seconds: number;
}

export interface StandingsResponse {
  data: StandingsData;
  meta: StandingsMeta;
}

/** Coerce a value to int; falls back to a sentinel when unparseable. */
function toInt(value: number | string | null | undefined, fallback: number): number {
  if (typeof value === 'number') return Number.isFinite(value) ? Math.trunc(value) : fallback;
  if (typeof value === 'string') {
    const n = Number.parseInt(value, 10);
    return Number.isFinite(n) ? n : fallback;
  }
  return fallback;
}

/**
 * Parse the raw API response into the coerced shape. Idempotent — calling
 * twice on the same payload returns the same coerced object.
 */
export function parseStandingsResponse(raw: {
  data: { season: number; teams: StandingsRecordRaw[] };
  meta: StandingsMeta;
}): StandingsResponse {
  const teams: StandingsRecord[] = raw.data.teams.map((t) => ({
    ...t,
    division_rank: toInt(t.division_rank, 999),
    league_rank: toInt(t.league_rank, 999),
  }));
  return {
    data: { season: raw.data.season, teams },
    meta: raw.meta,
  };
}
