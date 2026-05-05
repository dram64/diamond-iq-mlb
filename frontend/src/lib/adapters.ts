/**
 * Pure functions that convert API wire types (`@/types/api`) into the
 * internal application types (`@/types/app`).
 *
 * Components consume the internal types. The wire types stay in the API
 * layer (`@/lib/api`) and don't leak past these adapters. If the backend
 * ever changes shape, this file is the only place that needs updating
 * downstream of the type definitions themselves.
 */

import { getMlbTeam, type MlbTeam } from './mlbTeams';
import type {
  ApiContentItem,
  ApiContentResponse,
  ApiFeaturedItem,
  ApiGame,
  ApiLinescore,
  ApiTeam,
  ScoreboardResponse,
} from '@/types/api';
import type {
  AppContent,
  AppContentItem,
  AppFeaturedItem,
  AppGame,
  AppInningHalf,
  AppLinescore,
  AppTeam,
} from '@/types/app';

/**
 * Build an AppTeam, preferring the static MLB table for richer data
 * (full name, colors) and falling back to the API's reference shape
 * for any team id we don't recognize. Empty strings for colors when
 * unknown — components decide how to render that.
 */
export function apiTeamToTeam(apiTeam: ApiTeam): AppTeam {
  const known: MlbTeam | undefined = getMlbTeam(apiTeam.id);
  if (known) {
    return {
      id: known.id,
      abbreviation: known.abbreviation,
      locationName: known.locationName,
      teamName: known.teamName,
      fullName: known.fullName,
      primaryColor: known.primaryColor,
      secondaryColor: known.secondaryColor,
      logoPath: known.logoPath,
    };
  }
  // Unknown id — fall back to whatever the API returned. Better to render
  // a generic chip than crash.
  return {
    id: apiTeam.id,
    abbreviation: apiTeam.abbreviation,
    locationName: '',
    teamName: apiTeam.name,
    fullName: apiTeam.name,
    primaryColor: '',
    secondaryColor: '',
    logoPath: '',
  };
}

function inningHalfFromApi(half: ApiLinescore['inning_half']): AppInningHalf | undefined {
  if (half === 'Top') return 'top';
  if (half === 'Bottom') return 'bot';
  return undefined;
}

function nullishToOptional<T>(v: T | null | undefined): T | undefined {
  return v == null ? undefined : v;
}

function apiLinescoreToLinescore(api: ApiLinescore): AppLinescore {
  return {
    inning: nullishToOptional(api.inning),
    inningHalf: inningHalfFromApi(api.inning_half),
    balls: nullishToOptional(api.balls),
    strikes: nullishToOptional(api.strikes),
    outs: nullishToOptional(api.outs),
    awayRuns: nullishToOptional(api.away_runs),
    homeRuns: nullishToOptional(api.home_runs),
  };
}

/**
 * Convert one ApiGame into an AppGame.
 *
 * Live-only fields the backend doesn't yet provide (bases, batter,
 * pitcher, win probability) are intentionally left undefined; components
 * render placeholders rather than fictional data.
 */
export function apiGameToGame(apiGame: ApiGame): AppGame {
  return {
    id: apiGame.game_pk,
    date: apiGame.date,
    status: apiGame.status,
    detailedState: apiGame.detailed_state,
    away: apiTeamToTeam(apiGame.away),
    home: apiTeamToTeam(apiGame.home),
    awayScore: apiGame.away_score,
    homeScore: apiGame.home_score,
    venue: nullishToOptional(apiGame.venue),
    startTimeUtc: apiGame.start_time_utc,
    linescore: apiGame.linescore ? apiLinescoreToLinescore(apiGame.linescore) : undefined,
    // Backend doesn't supply these yet:
    bases: undefined,
    batter: undefined,
    pitcher: undefined,
    winProbability: undefined,
  };
}

export function apiScoreboardToGames(response: ScoreboardResponse): AppGame[] {
  return response.games.map(apiGameToGame);
}

/**
 * Merge multiple scoreboard responses (typically yesterday-UTC and today-UTC)
 * into a single deduplicated, sorted list of AppGame. Dedup is by `id`
 * (MLB game_pk); a game appears in only one date partition under normal
 * conditions, but defending against duplicates is cheap insurance.
 *
 * Sort order: ascending `startTimeUtc`. Stable across calls.
 */
export function mergeScoreboards(...responses: ScoreboardResponse[]): AppGame[] {
  const seen = new Set<number>();
  const merged: AppGame[] = [];
  for (const response of responses) {
    for (const apiGame of response.games) {
      if (seen.has(apiGame.game_pk)) continue;
      seen.add(apiGame.game_pk);
      merged.push(apiGameToGame(apiGame));
    }
  }
  merged.sort((a, b) => (a.startTimeUtc < b.startTimeUtc ? -1 : a.startTimeUtc > b.startTimeUtc ? 1 : 0));
  return merged;
}

// ── Daily AI content ────────────────────────────────────────────────

/**
 * Defensive ISO-8601 parsing. Backend writes a perfect string; falls back
 * to epoch-zero only if a future schema change ever drops the field, so
 * components can still render without crashing.
 */
function safeParseDate(iso: string | undefined | null): Date {
  if (!iso) return new Date(0);
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? new Date(0) : d;
}

export function adaptContentItem(wire: ApiContentItem): AppContentItem {
  return {
    text: wire.text ?? '',
    contentType: wire.content_type,
    modelId: wire.model_id ?? '',
    generatedAt: safeParseDate(wire.generated_at_utc),
    gamePk: wire.game_pk,
  };
}

export function adaptFeaturedItem(wire: ApiFeaturedItem): AppFeaturedItem {
  return {
    ...adaptContentItem(wire),
    contentType: 'FEATURED',
    rank: wire.rank,
  };
}

export function adaptContent(wire: ApiContentResponse): AppContent {
  return {
    date: wire.date,
    recap: (wire.recap ?? []).map(adaptContentItem),
    previews: (wire.previews ?? []).map(adaptContentItem),
    featured: (wire.featured ?? []).map(adaptFeaturedItem),
  };
}
