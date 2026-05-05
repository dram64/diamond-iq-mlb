export type FeaturedGameStatus = 'live' | 'final' | 'scheduled' | 'preview' | 'postponed';

export interface FeaturedGameProbablePitcher {
  id: number;
  full_name: string;
}

export interface FeaturedGameTeam {
  team_id: number;
  team_name: string;
  abbreviation: string;
  wins: number;
  losses: number;
  run_differential: number | null;
  probable_pitcher: FeaturedGameProbablePitcher | null;
}

export interface FeaturedGameData {
  date: string;
  game_pk: number;
  status: FeaturedGameStatus;
  detailed_state: string;
  start_time_utc: string;
  venue: string | null;
  away: FeaturedGameTeam;
  home: FeaturedGameTeam;
  selection_reason: string;
}

export interface FeaturedGameResponse {
  data: FeaturedGameData;
  meta: {
    season: number;
    timestamp: string;
    cache_max_age_seconds: number;
  };
}
