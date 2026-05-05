import type { TeamId } from './team';

export type GameStatus = 'live' | 'final' | 'scheduled';
export type InningHalf = 'top' | 'bot';
export type Leverage = 'low' | 'med' | 'high';

export interface Count {
  balls: number;
  strikes: number;
}

export interface Bases {
  first: boolean;
  second: boolean;
  third: boolean;
}

export interface GameTeamLive {
  id: TeamId;
  score: number;
  hits: number;
  errors: number;
}

export interface GameTeamFinal {
  id: TeamId;
  score: number;
}

export interface GameTeamScheduled {
  id: TeamId;
}

interface GameBase {
  id: string;
}

export interface LiveGame extends GameBase {
  status: 'live';
  inning: number;
  half: InningHalf;
  outs: number;
  away: GameTeamLive;
  home: GameTeamLive;
  bases: Bases;
  count: Count;
  batter: string;
  pitcher: string;
  leverage: Leverage;
  /** Home-team win probability, 0-100. */
  wp: number;
  venue?: string;
  startTime?: string;
  featured?: boolean;
}

export interface FinalGame extends GameBase {
  status: 'final';
  inning: number;
  away: GameTeamFinal;
  home: GameTeamFinal;
  /** Optional note, e.g. "F/10" for extras. */
  note?: string;
}

export interface ScheduledGame extends GameBase {
  status: 'scheduled';
  startTime: string;
  away: GameTeamScheduled;
  home: GameTeamScheduled;
  prob: {
    away: string;
    home: string;
  };
}

/** Discriminated union for any game in the slate, narrowed by `status`. */
export type Game = LiveGame | FinalGame | ScheduledGame;

export type PlayType =
  | 'atbat'
  | 'pitch'
  | 'hit'
  | 'out'
  | 'walk'
  | 'hr'
  | 'inning';

export interface PlayByPlayEntry {
  inning: number;
  half: InningHalf;
  desc: string;
  type: PlayType;
  /** True if this is the live/current play. */
  live?: boolean;
}

export type PitchType = 'FF' | 'SI' | 'SL' | 'CH' | 'CU' | 'FC' | 'KC';

export type PitchResult =
  | 'ball'
  | 'strike'
  | 'called-strike'
  | 'foul'
  | 'hit'
  | 'out';

export interface Pitch {
  /** Pitch number within the at-bat. */
  n: number;
  type: PitchType | string;
  mph: number;
  /** Horizontal position in [-1, 1] across strike zone. */
  x: number;
  /** Vertical position in [0, 1] bottom→top; > 1 is above zone. */
  y: number;
  result: PitchResult;
}

/** Upcoming-series card row on a team dashboard. */
export interface UpcomingGame {
  opp: TeamId;
  home: boolean;
  time: string;
  prob: string;
}

/** One row of the live-game matchup stat table (batter vs pitcher). */
export interface MatchupStatRow {
  label: string;
  batter: string;
  pitcher: string;
}

/** One pitch type in the pitcher's mix for a game. */
export interface PitchMixEntry {
  /** Display name, e.g. "4-seam", "Slider". */
  name: string;
  /** Usage percentage 0-100. */
  pct: number;
  /** Average velocity as printable string. */
  mph: string;
  /** Whiff rate as printable percent, e.g. "24%". */
  whiff: string;
}

/** Batter-handed label for the strike-zone view. */
export type BatterSide = 'L' | 'R';

/** Editorial analyst column contents for a game. */
export interface LiveAnalyst {
  topic: string;
  /** Paragraphs of body copy. First paragraph renders with full emphasis. */
  paragraphs: readonly string[];
  byline: string;
  ts: string;
}

/** All per-game detail the live tracker needs beyond the base Game record. */
export interface LiveGameDetail {
  batterSide: BatterSide;
  batterDetail: string;
  pitcherRole: string;
  pitcherDetail: string;
  pitcherLine: string;
  plays: readonly PlayByPlayEntry[];
  pitches: readonly Pitch[];
  matchup: readonly MatchupStatRow[];
  pitchMix: readonly PitchMixEntry[];
  analyst: LiveAnalyst;
}
