/**
 * Wire-shape types for the Diamond IQ HTTP API.
 *
 * These match the backend's `game_to_api_response()` exactly
 * (functions/shared/models.py). snake_case field names, integer
 * `game_pk`, scores at top level, optional nested `linescore`.
 *
 * Any change here MUST be synchronized with the backend types and
 * verified against a real API response — the types live in two
 * places by necessity (Python and TypeScript) and drift is silent
 * until something breaks at runtime.
 */

export interface ApiTeam {
  id: number;
  name: string;
  abbreviation: string;
}

export interface ApiLinescore {
  inning?: number | null;
  inning_half?: 'Top' | 'Bottom' | null;
  balls?: number | null;
  strikes?: number | null;
  outs?: number | null;
  away_runs?: number | null;
  home_runs?: number | null;
}

export type ApiGameStatus = 'live' | 'final' | 'scheduled' | 'preview' | 'postponed';

export interface ApiGame {
  game_pk: number;
  date: string; // yyyy-mm-dd (UTC date partition)
  status: ApiGameStatus;
  detailed_state: string;
  away: ApiTeam;
  home: ApiTeam;
  away_score: number;
  home_score: number;
  venue?: string | null;
  start_time_utc: string; // ISO 8601
  linescore?: ApiLinescore | null;
}

export interface ScoreboardResponse {
  date: string;
  count: number;
  games: ApiGame[];
}

export interface GameDetailResponse {
  game: ApiGame;
}

export interface ApiErrorBody {
  error: { code: string; message: string };
}

// ── /content/today ──────────────────────────────────────────────────

export type ApiContentType = 'RECAP' | 'PREVIEW' | 'FEATURED';

export interface ApiContentItem {
  text: string;
  content_type: ApiContentType;
  model_id: string;
  generated_at_utc: string; // ISO 8601
  game_pk: number;
}

export interface ApiFeaturedItem extends ApiContentItem {
  content_type: 'FEATURED';
  rank: number;
}

export interface ApiContentResponse {
  date: string;
  recap: ApiContentItem[];
  previews: ApiContentItem[];
  featured: ApiFeaturedItem[];
}

// ── WebSocket score updates ───────────────────────────────

/** Wire shape of a single field's diff: {old, new}. */
export interface ApiScoreUpdateFieldDiff<T = unknown> {
  old: T | null | undefined;
  new: T | null | undefined;
}

/** Wire shape of the linescore-nested diff. Each present key is a changed field. */
export interface ApiScoreUpdateLinescoreChanges {
  inning?: ApiScoreUpdateFieldDiff<number>;
  inning_half?: ApiScoreUpdateFieldDiff<string>;
  inning_state?: ApiScoreUpdateFieldDiff<string>;
  balls?: ApiScoreUpdateFieldDiff<number>;
  strikes?: ApiScoreUpdateFieldDiff<number>;
  outs?: ApiScoreUpdateFieldDiff<number>;
  bases?: ApiScoreUpdateFieldDiff<unknown>;
}

/** Top-level changes object. Each present key is a changed top-level field. */
export interface ApiScoreUpdateChanges {
  away_score?: ApiScoreUpdateFieldDiff<number>;
  home_score?: ApiScoreUpdateFieldDiff<number>;
  status?: ApiScoreUpdateFieldDiff<ApiGameStatus>;
  detailed_state?: ApiScoreUpdateFieldDiff<string>;
  winProbability?: ApiScoreUpdateFieldDiff<number>;
  linescore?: ApiScoreUpdateLinescoreChanges;
}

/**
 * Full wire shape of a score_update message pushed by the stream-processor
 * Lambda over the WebSocket connection. The `type` field is reserved as the
 * discriminant for future message types (e.g., 'recap_published').
 */
export interface ApiScoreUpdateMessage {
  type: 'score_update';
  game_pk: number;
  timestamp: string;
  changes: ApiScoreUpdateChanges;
}
