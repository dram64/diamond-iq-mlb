export interface TeamStatsBlock {
  /** Catch-all — every numeric or string stat the API returns lives here. */
  [key: string]: unknown;
}

export interface TeamStats {
  team_id: number;
  team_name: string;
  season: number;
  hitting: TeamStatsBlock;
  pitching: TeamStatsBlock;
}

export interface TeamStatsMeta {
  season: number;
  timestamp: string;
  cache_max_age_seconds: number;
}

export interface TeamStatsResponse {
  data: TeamStats;
  meta: TeamStatsMeta;
}

export interface TeamCompareData {
  season: number;
  teams: TeamStats[];
}

export interface TeamCompareResponse {
  data: TeamCompareData;
  meta: TeamStatsMeta;
}
