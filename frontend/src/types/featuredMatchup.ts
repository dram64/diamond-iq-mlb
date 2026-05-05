export type FeaturedMatchupLeague = 'AL' | 'NL' | 'MLB';

export interface FeaturedMatchupHighlightStats {
  avg: string | null;
  ops: string | null;
  era: string | null;
  whip: string | null;
}

export interface FeaturedMatchupTeam {
  team_id: number;
  team_name: string | null;
  abbreviation: string | null;
  league: FeaturedMatchupLeague;
  wins: number;
  losses: number;
  games_back: string | null;
  run_differential: number | null;
  highlight_stats: FeaturedMatchupHighlightStats;
}

export interface FeaturedMatchupData {
  date: string;
  team_ids: [number, number];
  teams: [FeaturedMatchupTeam, FeaturedMatchupTeam];
  selection_reason: string;
}

export interface FeaturedMatchupResponse {
  data: FeaturedMatchupData;
  meta: {
    season: number;
    timestamp: string;
    cache_max_age_seconds: number;
  };
}
