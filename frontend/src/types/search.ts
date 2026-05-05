export interface PlayerSearchHit {
  person_id: number;
  full_name: string | null;
  primary_position_abbr: string | null;
  primary_number: string | null;
}

export interface PlayerSearchData {
  query: string;
  results: PlayerSearchHit[];
  count: number;
}

export interface PlayerSearchResponse {
  data: PlayerSearchData;
  meta: {
    season: number;
    timestamp: string;
    cache_max_age_seconds: number;
  };
}
