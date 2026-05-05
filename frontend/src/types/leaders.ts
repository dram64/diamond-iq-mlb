export type LeaderGroup = 'hitting' | 'pitching';

/** One leader row. The API guarantees person_id, full_name, and rank;
 *  every other field is the stat that was queried plus optional metadata. */
export interface LeaderRecord {
  person_id: number;
  full_name: string;
  team_id?: number;
  rank: number;
  /** Numeric stat values (woba, ops_plus, fip, hr, rbi, k, wins, saves). */
  woba?: number;
  ops_plus?: number;
  fip?: number;
  home_runs?: number;
  rbi?: number;
  strikeouts?: number;
  wins?: number;
  saves?: number;
  /** Pre-formatted rate stats from the API. */
  avg?: string;
  obp?: string;
  slg?: string;
  ops?: string;
  era?: string;
  whip?: string;
  /** Catch-all for any field the backend adds without a frontend update. */
  [key: string]: unknown;
}

export interface LeadersData {
  group: LeaderGroup;
  stat: string;
  /** The actual stored attribute name (URL token may differ — e.g. "k" → "strikeouts"). */
  field: string;
  direction: 'asc' | 'desc';
  limit: number;
  leaders: LeaderRecord[];
}

export interface LeadersMeta {
  season: number;
  timestamp: string;
  cache_max_age_seconds: number;
}

export interface LeadersResponse {
  data: LeadersData;
  meta: LeadersMeta;
}
