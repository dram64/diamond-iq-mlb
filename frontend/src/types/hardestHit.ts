export interface HardestHitRecord {
  game_pk: number;
  batter_id: number;
  batter_name: string;
  inning?: number | null;
  half_inning?: 'top' | 'bottom' | string | null;
  result_event?: string | null;
  result_event_type?: string | null;
  launch_speed: number;
  launch_angle?: number | null;
  total_distance?: number | null;
  trajectory?: string | null;
  ttl?: number;
}

export interface HardestHitData {
  date: string;
  limit: number;
  hits: HardestHitRecord[];
}

export interface HardestHitMeta {
  season: number;
  timestamp: string;
  cache_max_age_seconds: number;
}

export interface HardestHitResponse {
  data: HardestHitData;
  meta: HardestHitMeta;
}
