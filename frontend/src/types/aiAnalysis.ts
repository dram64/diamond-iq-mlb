export type AICompareKind = 'players' | 'teams';

export interface AICompareData {
  kind: AICompareKind;
  ids: number[];
  text: string;
  model_id: string;
  generated_at: string;
  cache_hit: boolean;
}

export interface AICompareResponse {
  data: AICompareData;
  meta: {
    season: number;
    timestamp: string;
    cache_max_age_seconds: number;
  };
}
