/**
 * HTTP client for the Diamond IQ backend.
 *
 * Thin wrapper over `fetch` that:
 *   - prefixes every URL with `API_URL`
 *   - applies a 5s timeout via `AbortSignal.timeout`
 *   - throws a typed `ApiError` for any non-2xx, network failure, or timeout
 *   - returns the parsed JSON body on success
 *
 * Response shapes match the backend's `game_to_api_response` exactly
 * (snake_case, integer game_pk, scores at top level, linescore nested).
 */

import { API_URL } from './env';
import type {
  ApiContentResponse,
  ApiErrorBody,
  GameDetailResponse,
  ScoreboardResponse,
} from '@/types/api';
import type { AICompareKind, AICompareResponse } from '@/types/aiAnalysis';
import type { CompareResponse } from '@/types/compare';
import type { FeaturedGameResponse } from '@/types/featuredGame';
import type { FeaturedMatchupResponse } from '@/types/featuredMatchup';
import type { HardestHitResponse } from '@/types/hardestHit';
import type { LeaderGroup, LeadersResponse } from '@/types/leaders';
import type { PlayerSearchResponse } from '@/types/search';
import { parseStandingsResponse, type StandingsResponse } from '@/types/standings';
import type { TeamCompareResponse, TeamStatsResponse } from '@/types/teamStats';

const DEFAULT_TIMEOUT_MS = 5000;

export class ApiError extends Error {
  readonly status: number;
  readonly url: string;
  /** Server-supplied error code (e.g. "off_day", "data_not_yet_available")
   *  pulled from `body.error.code`. Null on network errors and on
   *  non-JSON responses. */
  readonly code: string | null;

  constructor(
    message: string,
    opts: { status: number; url: string; code?: string | null; cause?: unknown },
  ) {
    super(message);
    this.name = 'ApiError';
    this.status = opts.status;
    this.url = opts.url;
    this.code = opts.code ?? null;
    if (opts.cause !== undefined) {
      (this as { cause?: unknown }).cause = opts.cause;
    }
  }
}

// ── Public client ───────────────────────────────────────────────────────

interface RequestOptions {
  signal?: AbortSignal;
  timeoutMs?: number;
}

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const url = `${API_URL}${path}`;
  const timeoutMs = opts.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const signal = opts.signal ?? AbortSignal.timeout(timeoutMs);

  let response: Response;
  try {
    response = await fetch(url, { signal, headers: { Accept: 'application/json' } });
  } catch (err) {
    // AbortError on timeout, TypeError on network failure (DNS, offline, etc.)
    const isTimeout =
      err instanceof DOMException && (err.name === 'TimeoutError' || err.name === 'AbortError');
    throw new ApiError(isTimeout ? `Request timed out after ${timeoutMs}ms: ${url}` : `Network error: ${url}`, {
      status: 0,
      url,
      cause: err,
    });
  }

  if (!response.ok) {
    let bodyMessage = `${response.status} ${response.statusText}`;
    let bodyCode: string | null = null;
    try {
      const body = (await response.json()) as Partial<ApiErrorBody>;
      if (body?.error?.message) bodyMessage = body.error.message;
      if (body?.error?.code) bodyCode = body.error.code;
    } catch {
      // body wasn't JSON; keep the status text
    }
    throw new ApiError(bodyMessage, { status: response.status, url, code: bodyCode });
  }

  return (await response.json()) as T;
}

/** Fetch the scoreboard for one date (YYYY-MM-DD). Defaults to UTC today server-side. */
export function fetchScoreboard(
  date?: string,
  opts: RequestOptions = {},
): Promise<ScoreboardResponse> {
  const query = date ? `?date=${encodeURIComponent(date)}` : '';
  return request<ScoreboardResponse>(`/scoreboard/today${query}`, opts);
}

/** Fetch a single game by its MLB gamePk. Date is required (no GSI yet). */
export function fetchGame(
  gameId: number,
  date: string,
  opts: RequestOptions = {},
): Promise<GameDetailResponse> {
  const query = `?date=${encodeURIComponent(date)}`;
  return request<GameDetailResponse>(`/games/${encodeURIComponent(String(gameId))}${query}`, opts);
}

/** Fetch the day's AI-generated recap, previews, and featured matchups. */
export function fetchDailyContent(
  date?: string,
  opts: RequestOptions = {},
): Promise<ApiContentResponse> {
  const query = date ? `?date=${encodeURIComponent(date)}` : '';
  return request<ApiContentResponse>(`/content/today${query}`, opts);
}

/** Fetch top-N leaders for a (group, stat) pair. URL stat tokens may differ
 *  from storage attribute names (e.g. "k" → strikeouts); see . */
export function fetchLeaders(
  group: LeaderGroup,
  stat: string,
  limit = 5,
  opts: RequestOptions = {},
): Promise<LeadersResponse> {
  const path = `/api/leaders/${encodeURIComponent(group)}/${encodeURIComponent(stat)}?limit=${limit}`;
  return request<LeadersResponse>(path, opts);
}

/** Fetch a side-by-side comparison for 2-4 MLB person IDs. */
export function fetchCompare(
  ids: readonly number[],
  opts: RequestOptions = {},
): Promise<CompareResponse> {
  const csv = ids.join(',');
  return request<CompareResponse>(`/api/players/compare?ids=${csv}`, opts);
}

/** Fetch the top-N hardest-hit balls for a date (YYYY-MM-DD). Returns 503
 *  with error.code="data_not_yet_available" when the HITS#<date> partition
 *  is empty (cron hasn't fired for that date or future date). */
export function fetchHardestHit(
  date: string,
  limit?: number,
  opts: RequestOptions = {},
): Promise<HardestHitResponse> {
  const query = limit ? `?limit=${limit}` : '';
  return request<HardestHitResponse>(`/api/hardest-hit/${date}${query}`, opts);
}

/** Fetch division standings for a season. Coerces string-typed numeric fields
 *  (division_rank, league_rank) to numbers at the parse boundary; see
 *  types/standings.ts for the convention. */
export async function fetchStandings(
  season: number,
  opts: RequestOptions = {},
): Promise<StandingsResponse> {
  const raw = await request<Parameters<typeof parseStandingsResponse>[0]>(
    `/api/standings/${season}`,
    opts,
  );
  return parseStandingsResponse(raw);
}

/** Fetch a single team's hitting + pitching season aggregates. */
export function fetchTeamStats(
  teamId: number,
  opts: RequestOptions = {},
): Promise<TeamStatsResponse> {
  return request<TeamStatsResponse>(`/api/teams/${teamId}/stats`, opts);
}

interface RosterResponse {
  data: {
    team_id: number;
    roster: Array<{
      person_id: number;
      full_name: string;
      position_abbr: string;
      jersey_number?: string | null;
      status_code?: string | null;
    }>;
  };
  meta: { season: number; timestamp: string; cache_max_age_seconds: number };
}

/** Fetch a team's active roster. */
export function fetchRoster(
  teamId: number,
  opts: RequestOptions = {},
): Promise<RosterResponse> {
  return request<RosterResponse>(`/api/teams/${teamId}/roster`, opts);
}

/** Fetch a side-by-side comparison for 2-4 MLB team IDs. */
export function fetchTeamCompare(
  ids: readonly number[],
  opts: RequestOptions = {},
): Promise<TeamCompareResponse> {
  const csv = ids.join(',');
  return request<TeamCompareResponse>(`/api/teams/compare?ids=${csv}`, opts);
}

/** Fetch the daily-rotating featured player matchup. */
export function fetchFeaturedMatchup(
  opts: RequestOptions = {},
): Promise<FeaturedMatchupResponse> {
  return request<FeaturedMatchupResponse>(`/api/featured-matchup`, opts);
}

/** Fetch today's spotlit MLB game.
 *
 * 503 with code "off_day" or "data_not_yet_available" both indicate the
 * frontend should render the off-day banner. ApiError carries the code
 * via its details payload — the hook branches on it.
 */
export function fetchFeaturedGame(
  opts: RequestOptions = {},
): Promise<FeaturedGameResponse> {
  return request<FeaturedGameResponse>(`/api/games/featured`, opts);
}

/** Search players by name substring (— typeahead). */
export function fetchPlayerSearch(
  query: string,
  limit = 10,
  opts: RequestOptions = {},
): Promise<PlayerSearchResponse> {
  const q = encodeURIComponent(query);
  return request<PlayerSearchResponse>(`/api/players/search?q=${q}&limit=${limit}`, opts);
}

/** Fetch Bedrock-generated comparison commentary. */
export function fetchAICompareAnalysis(
  kind: AICompareKind,
  ids: readonly number[],
  opts: RequestOptions = {},
): Promise<AICompareResponse> {
  const csv = ids.join(',');
  // Bedrock latency p95 can hit ~5-6s; default 5s timeout would race.
  return request<AICompareResponse>(`/api/compare-analysis/${kind}?ids=${csv}`, {
    ...opts,
    timeoutMs: opts.timeoutMs ?? 12_000,
  });
}
