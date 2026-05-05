export interface ComparePlayerMetadata {
  person_id: number;
  full_name: string;
  primary_number?: string;
  current_age?: number;
  height?: string;
  weight?: number;
  bat_side?: string;
  pitch_hand?: string;
  primary_position_abbr?: string;
}

export interface ComparePlayerStats {
  /** Catch-all — every numeric or string stat the API returns lives here. */
  [key: string]: unknown;
}

export interface ComparePlayer {
  person_id: number;
  metadata: ComparePlayerMetadata;
  hitting: ComparePlayerStats | null;
  pitching: ComparePlayerStats | null;
  /** Optional career-awards summary. Null/undefined if the awards
   *  ingest cron hasn't yet populated AWARDS#GLOBAL for this player. */
  awards?: PlayerAwardsBlock | null;
  /** Optional Baseball Savant Statcast block. Null/undefined if
   *  the player isn't in the qualified pool for any of the 5 leaderboards
   *  the ingest reads. */
  statcast?: StatcastBlock | null;
}

export interface StatcastHitting {
  xba?: string | null;
  xslg?: string | null;
  xwoba?: string | null;
  avg_hit_speed?: number | string | null;
  max_hit_speed?: number | string | null;
  ev95_percent?: number | string | null;
  barrel_percent?: number | string | null;
  barrel_per_pa_percent?: number | string | null;
  sweet_spot_percent?: number | string | null;
  sprint_speed?: number | string | null;
  max_distance?: number | string | null;
  avg_distance?: number | string | null;
  avg_hr_distance?: number | string | null;
}

export interface StatcastPitching {
  xera?: number | string | null;
  xba_against?: string | null;
  whiff_percent?: number | string | null;
  chase_whiff_percent?: number | string | null;
  fastball_avg_speed?: number | string | null;
  fastball_avg_spin?: number | string | null;
}

export interface StatcastBatTracking {
  avg_bat_speed?: number | string | null;
  swing_length?: number | string | null;
  hard_swing_rate?: number | string | null;
  squared_up_per_swing?: number | string | null;
  blast_per_swing?: number | string | null;
}

export interface StatcastBattedBall {
  pull_rate?: number | string | null;
  straight_rate?: number | string | null;
  oppo_rate?: number | string | null;
  gb_rate?: number | string | null;
  fb_rate?: number | string | null;
  ld_rate?: number | string | null;
}

export interface StatcastBlock {
  person_id: number;
  season: number;
  display_name?: string | null;
  hitting: StatcastHitting | null;
  pitching: StatcastPitching | null;
  bat_tracking: StatcastBatTracking | null;
  batted_ball: StatcastBattedBall | null;
}

export interface PlayerAwardsBlock {
  person_id: number;
  total_awards: number;
  all_star_count: number;
  all_star_years: number[];
  mvp_count: number;
  mvp_years: number[];
  cy_young_count: number;
  cy_young_years: number[];
  rookie_of_the_year_count: number;
  rookie_of_the_year_years: number[];
  gold_glove_count: number;
  gold_glove_years: number[];
  silver_slugger_count: number;
  silver_slugger_years: number[];
  world_series_count: number;
  world_series_years: number[];
}

export interface CompareData {
  players: ComparePlayer[];
}

export interface CompareMeta {
  season: number;
  timestamp: string;
  cache_max_age_seconds: number;
}

export interface CompareResponse {
  data: CompareData;
  meta: CompareMeta;
}
