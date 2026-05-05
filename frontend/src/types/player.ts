import type { TeamId } from './team';

export type PlayerId = string;
export type BatsThrows = 'L' | 'R' | 'S';
export type Position = 'C' | '1B' | '2B' | '3B' | 'SS' | 'LF' | 'CF' | 'RF' | 'DH' | 'SP' | 'RP';
export type PlayerEra = 'current' | 'classic';
export type SprayPattern = 'pull-L' | 'pull-R' | 'balanced-L' | 'balanced-R';

export interface CareerTotals {
  g: number;
  ab: number;
  h: number;
  hr: number;
  rbi: number;
  sb: number;
  avg: number;
  obp: number;
  slg: number;
  ops: number;
  war: number;
}

export interface SeasonStats {
  year: number;
  avg: number;
  hr: number;
  war: number;
  obp: number;
  slg: number;
}

export interface Player {
  id: PlayerId;
  first: string;
  last: string;
  /** Team id, or "—" for retired/unaffiliated players. */
  team: TeamId | '—';
  pos: Position | string;
  bats: BatsThrows;
  throws: BatsThrows;
  /** Birth year as string. */
  born: string;
  era: PlayerEra;
  number: number;
  tagline: string;
  career: CareerTotals;
  seasonByYear: SeasonStats[];
  spray: SprayPattern;
}

/** Leaderboard entry for any stat; `highlight` stats depend on the view. */
export interface LeaderboardRow {
  rank: number;
  name: string;
  team: TeamId;
  era: string;
  g: number;
  war: number;
  avg: number;
  hr: number;
  ops: number;
}

export interface BattingLeader {
  name: string;
  team: TeamId;
  avg: number;
  hr: number;
  rbi: number;
  war: number;
  trend: number[];
}

export interface PitchingLeader {
  name: string;
  team: TeamId;
  era: number;
  wl: string;
  k: number;
  whip: number;
  trend: number[];
}

export interface HardestHitEntry {
  name: string;
  team: TeamId;
  mph: number;
  result: string;
}

/** Roster row on the team dashboard (top performers / strugglers). */
export interface PerformerRow {
  name: string;
  pos: string;
  /** Printable stat line, e.g. ".326 / 25 HR / 5.8 WAR". */
  line: string;
  trend: number[];
}

/** Side of a two-player compare preview. */
export interface ComparePreviewSide {
  name: string;
  team: TeamId;
  pos: Position | string;
  stats: Record<string, number>;
}
