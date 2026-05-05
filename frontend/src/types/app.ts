/**
 * Internal application types — the shape components consume after the
 * adapter layer has bridged the wire types in `./api.ts`.
 *
 * Compared to the wire shape:
 *   - `id` is the MLB `game_pk` (kept as integer)
 *   - Team objects are richer: full name, location, primary/secondary
 *     colors from the static MLB table (`@/lib/mlbTeams.ts`)
 *   - Live-only fields the backend doesn't yet supply (bases, count,
 *     batter, pitcher, win probability) are present as `undefined`,
 *     so components can render "—" placeholders without crashing
 *
 * When the backend serves these missing fields, the adapter fills them
 * in and components light up — no shape changes here.
 */

export type AppGameStatus = 'live' | 'final' | 'scheduled' | 'preview' | 'postponed';

export type AppInningHalf = 'top' | 'bot';

export interface AppTeam {
  /** MLB Stats API team id (integer). Kept as number to match the wire shape. */
  id: number;
  abbreviation: string;
  /** "New York" — from the MLB table when known, falls back to API's name when not. */
  locationName: string;
  /** "Yankees" — likewise. */
  teamName: string;
  /** Static path to the team's cap-logo SVG, or empty string when unknown. */
  logoPath: string;
  /** "New York Yankees" — likewise. */
  fullName: string;
  /** Hex color from the official MLB brand guide. Empty string when unknown. */
  primaryColor: string;
  /** Hex color from the official MLB brand guide. Empty string when unknown. */
  secondaryColor: string;
}

export interface AppLinescore {
  inning?: number;
  inningHalf?: AppInningHalf;
  balls?: number;
  strikes?: number;
  outs?: number;
  awayRuns?: number;
  homeRuns?: number;
}

/** Optional bases-occupied state. Backend doesn't yet supply this; will be filled in when it does. */
export interface AppBases {
  first: boolean;
  second: boolean;
  third: boolean;
}

export interface AppGame {
  /** MLB game_pk; unique across all games. */
  id: number;
  /** UTC date partition the game is keyed under (yyyy-mm-dd). */
  date: string;
  status: AppGameStatus;
  /** MLB's free-form status string ("In Progress", "Pre-Game", "Postponed: Rain", etc.). */
  detailedState: string;

  away: AppTeam;
  home: AppTeam;
  awayScore: number;
  homeScore: number;

  venue?: string;
  /** ISO 8601 first-pitch time, exactly as MLB returned it. */
  startTimeUtc: string;

  /** Inning, half, balls/strikes/outs, runs by team — only populated when the game has a linescore. */
  linescore?: AppLinescore;

  // ── Fields the backend doesn't yet supply. Will become populated as the
  // ── ingestion expands; components handle `undefined` with placeholders.

  /** Bases-occupied state. Undefined until backend ingests live play state. */
  bases?: AppBases;
  /** Current at-bat batter name. Undefined until backend ingests it. */
  batter?: string;
  /** Current at-bat pitcher name. Undefined until backend ingests it. */
  pitcher?: string;
  /** Home-team win probability, 0-100. Undefined until backend ingests it. */
  winProbability?: number;
}

// ── Daily AI content ────────────────────────────────────────────────

export type AppContentType = 'RECAP' | 'PREVIEW' | 'FEATURED';

export interface AppContentItem {
  text: string;
  contentType: AppContentType;
  modelId: string;
  generatedAt: Date;
  gamePk: number;
}

export interface AppFeaturedItem extends AppContentItem {
  contentType: 'FEATURED';
  rank: number;
}

export interface AppContent {
  /** UTC date the content was generated for (yyyy-mm-dd). */
  date: string;
  recap: AppContentItem[];
  previews: AppContentItem[];
  /** Sorted by rank ascending (1, 2). Backend guarantees this. */
  featured: AppFeaturedItem[];
}
