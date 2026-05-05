/** A club identifier (e.g. "STR", "KNG"). Opaque three-letter code. */
export type TeamId = string;

export interface Team {
  id: TeamId;
  city: string;
  name: string;
  abbr: string;
  /** Primary club color as hex, e.g. "#4a6b7a". */
  color: string;
  /** Win-loss record as printable string, e.g. "78-52". */
  rec: string;
  /** Winning percentage in [0, 1]. */
  pct: number;
}

/** Flat row for the league-standings table on the home screen. */
export interface StandingsRow {
  team: TeamId;
  rec: string;
  gb: string;
  /** Run differential as signed printable string (e.g. "+112"). */
  rd: string;
  l10: string;
}

/** Division/league standings row with additional detail. */
export interface DivisionStandingsRow {
  team: TeamId;
  rec: string;
  pct: number;
  gb: string;
  l10: string;
  strk: string;
}

/** Compact team-grid entry with playoff odds. */
export interface TeamGridEntry {
  id: TeamId;
  rec: string;
  l10: string;
  strk: string;
  /** Playoff odds, 0-100. */
  odds: number;
}
