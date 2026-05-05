import type { ComparePlayer } from '@/types/compare';
import type { TeamStats } from '@/types/teamStats';

export interface StatRef {
  /** Display label on the radar axis + the numerical-detail table. */
  label: string;
  /** Stable token used for animation delays + ascending-stat lookup. */
  token: string;
  /** True when lower is better (xERA / xBA against / WHIP). */
  ascending?: boolean;
  /** Pure value-extractor pulling from the most informative source on
   *  the ComparePlayer (Statcast block first, then season aggregates). */
  pick: (p: ComparePlayer) => number | null;
  /** Display formatter. Returns "—" for null inputs. */
  format: (v: number | null) => string;
  /** Notional MLB league baseline for the percentile approximation —
   *  a real percentile API replaces this in a future phase. Pair =
   *  (p10, p90) tail values; for ascending stats, p10 is the high-bad
   *  value and p90 is the low-good value (intentionally inverted). */
  percentileBaseline?: { p10: number; p90: number };
}

export interface TeamStatRef {
  label: string;
  token: string;
  ascending?: boolean;
  pick: (t: TeamStats) => number | null;
  format: (v: number | null) => string;
  percentileBaseline?: { p10: number; p90: number };
}

const toNum = (v: number | string | null | undefined): number | null => {
  if (v == null || v === '') return null;
  if (typeof v === 'number') return Number.isFinite(v) ? v : null;
  const n = Number.parseFloat(String(v));
  return Number.isFinite(n) ? n : null;
};

const fmtRate3 = (v: number | null): string => {
  if (v == null) return '—';
  return v < 1 ? v.toFixed(3).replace(/^0\./, '.') : v.toFixed(3);
};

const fmtFloat = (decimals: number) => (v: number | null): string =>
  v == null ? '—' : v.toFixed(decimals);

const fmtInt = (v: number | null): string => (v == null ? '—' : Math.round(v).toString());

const fmtPercent1 = (v: number | null): string => (v == null ? '—' : `${v.toFixed(1)}%`);

const fmtRateOf1 = (v: number | null): string => {
  if (v == null) return '—';
  return `${(v * 100).toFixed(1)}%`;
};

// ── Player radar — six hero hitter axes ────────────────────────────────

export const PLAYER_RADAR_STATS: StatRef[] = [
  {
    label: 'Avg EV',
    token: 'avg_hit_speed',
    pick: (p) => toNum(p.statcast?.hitting?.avg_hit_speed),
    format: fmtFloat(1),
    percentileBaseline: { p10: 86, p90: 95 },
  },
  {
    label: 'Hard-hit %',
    token: 'ev95_percent',
    pick: (p) => toNum(p.statcast?.hitting?.ev95_percent),
    format: fmtPercent1,
    percentileBaseline: { p10: 28, p90: 55 },
  },
  {
    label: 'Barrel %',
    token: 'barrel_percent',
    pick: (p) => toNum(p.statcast?.hitting?.barrel_percent),
    format: fmtPercent1,
    percentileBaseline: { p10: 3, p90: 22 },
  },
  {
    label: 'xwOBA',
    token: 'xwoba',
    pick: (p) => toNum(p.statcast?.hitting?.xwoba),
    format: fmtRate3,
    percentileBaseline: { p10: 0.28, p90: 0.42 },
  },
  {
    label: 'Sprint speed',
    token: 'sprint_speed',
    pick: (p) => toNum(p.statcast?.hitting?.sprint_speed),
    format: fmtFloat(1),
    percentileBaseline: { p10: 25.0, p90: 29.5 },
  },
  {
    label: 'OPS',
    token: 'ops',
    pick: (p) => toNum(p.hitting?.ops as number | string | undefined),
    format: fmtRate3,
    percentileBaseline: { p10: 0.65, p90: 0.95 },
  },
];

// ── Player numerical-detail table — fuller stat set, grouped ──────────

export interface StatGroup {
  title: string;
  rows: StatRef[];
}

export const PLAYER_DETAIL_GROUPS: StatGroup[] = [
  {
    title: 'Hitting',
    rows: [
      {
        label: 'AVG',
        token: 'avg',
        pick: (p) => toNum(p.hitting?.avg as string | number | undefined),
        format: fmtRate3,
      },
      {
        label: 'HR',
        token: 'home_runs',
        pick: (p) => toNum(p.hitting?.home_runs as number | undefined),
        format: fmtInt,
      },
      {
        label: 'RBI',
        token: 'rbi',
        pick: (p) => toNum(p.hitting?.rbi as number | undefined),
        format: fmtInt,
      },
      {
        label: 'OPS',
        token: 'ops',
        pick: (p) => toNum(p.hitting?.ops as string | number | undefined),
        format: fmtRate3,
      },
    ],
  },
  {
    title: 'Pitching',
    rows: [
      {
        label: 'ERA',
        token: 'era',
        ascending: true,
        pick: (p) => toNum(p.pitching?.era as string | number | undefined),
        format: fmtFloat(2),
      },
      {
        label: 'K',
        token: 'strikeouts',
        pick: (p) => toNum(p.pitching?.strikeouts as number | undefined),
        format: fmtInt,
      },
      {
        label: 'WHIP',
        token: 'whip',
        ascending: true,
        pick: (p) => toNum(p.pitching?.whip as string | number | undefined),
        format: fmtFloat(2),
      },
      {
        label: 'Wins',
        token: 'wins',
        pick: (p) => toNum(p.pitching?.wins as number | undefined),
        format: fmtInt,
      },
    ],
  },
  {
    title: 'Statcast — quality of contact',
    rows: [
      {
        label: 'Avg EV',
        token: 'avg_hit_speed',
        pick: (p) => toNum(p.statcast?.hitting?.avg_hit_speed),
        format: fmtFloat(1),
      },
      {
        label: 'Max EV',
        token: 'max_hit_speed',
        pick: (p) => toNum(p.statcast?.hitting?.max_hit_speed),
        format: fmtFloat(1),
      },
      {
        label: 'Barrel %',
        token: 'barrel_percent',
        pick: (p) => toNum(p.statcast?.hitting?.barrel_percent),
        format: fmtPercent1,
      },
      {
        label: 'Hard-hit %',
        token: 'ev95_percent',
        pick: (p) => toNum(p.statcast?.hitting?.ev95_percent),
        format: fmtPercent1,
      },
    ],
  },
  {
    title: 'Statcast — expected stats',
    rows: [
      {
        label: 'xBA',
        token: 'xba',
        pick: (p) => toNum(p.statcast?.hitting?.xba),
        format: fmtRate3,
      },
      {
        label: 'xSLG',
        token: 'xslg',
        pick: (p) => toNum(p.statcast?.hitting?.xslg),
        format: fmtRate3,
      },
      {
        label: 'xwOBA',
        token: 'xwoba',
        pick: (p) => toNum(p.statcast?.hitting?.xwoba),
        format: fmtRate3,
      },
      {
        label: 'Sprint speed',
        token: 'sprint_speed',
        pick: (p) => toNum(p.statcast?.hitting?.sprint_speed),
        format: fmtFloat(1),
      },
    ],
  },
  {
    title: 'Statcast — pitcher arsenal',
    rows: [
      {
        label: 'Fastball velo',
        token: 'fastball_avg_speed',
        pick: (p) => toNum(p.statcast?.pitching?.fastball_avg_speed),
        format: fmtFloat(1),
      },
      {
        label: 'Fastball spin',
        token: 'fastball_avg_spin',
        pick: (p) => toNum(p.statcast?.pitching?.fastball_avg_spin),
        format: fmtInt,
      },
      {
        label: 'Whiff %',
        token: 'whiff_percent',
        pick: (p) => toNum(p.statcast?.pitching?.whiff_percent),
        format: fmtPercent1,
      },
      {
        label: 'xERA',
        token: 'xera',
        ascending: true,
        pick: (p) => toNum(p.statcast?.pitching?.xera),
        format: fmtFloat(2),
      },
    ],
  },
  {
    title: 'Spray',
    rows: [
      {
        label: 'Pull %',
        token: 'pull_rate',
        pick: (p) => toNum(p.statcast?.batted_ball?.pull_rate),
        format: fmtRateOf1,
      },
      {
        label: 'Center %',
        token: 'straight_rate',
        pick: (p) => toNum(p.statcast?.batted_ball?.straight_rate),
        format: fmtRateOf1,
      },
      {
        label: 'Oppo %',
        token: 'oppo_rate',
        pick: (p) => toNum(p.statcast?.batted_ball?.oppo_rate),
        format: fmtRateOf1,
      },
    ],
  },
];

// ── Team radar — six aggregate axes ────────────────────────────────────

export const TEAM_RADAR_STATS: TeamStatRef[] = [
  {
    label: 'Team OPS',
    token: 'ops',
    pick: (t) => toNum((t.hitting as Record<string, unknown> | null)?.ops as string | number | null | undefined),
    format: fmtRate3,
    percentileBaseline: { p10: 0.66, p90: 0.78 },
  },
  {
    label: 'Team AVG',
    token: 'avg',
    pick: (t) => toNum((t.hitting as Record<string, unknown> | null)?.avg as string | number | null | undefined),
    format: fmtRate3,
    percentileBaseline: { p10: 0.225, p90: 0.265 },
  },
  {
    label: 'Stolen bases',
    token: 'stolen_bases',
    pick: (t) => toNum((t.hitting as Record<string, unknown> | null)?.stolen_bases as number | null | undefined),
    format: fmtInt,
    percentileBaseline: { p10: 12, p90: 45 },
  },
  {
    label: 'Team ERA',
    token: 'era',
    ascending: true,
    pick: (t) => toNum((t.pitching as Record<string, unknown> | null)?.era as string | number | null | undefined),
    format: fmtFloat(2),
    percentileBaseline: { p10: 4.8, p90: 3.0 },
  },
  {
    label: 'Team WHIP',
    token: 'whip',
    ascending: true,
    pick: (t) => toNum((t.pitching as Record<string, unknown> | null)?.whip as string | number | null | undefined),
    format: fmtFloat(2),
    percentileBaseline: { p10: 1.45, p90: 1.10 },
  },
  {
    label: 'OPP AVG',
    token: 'opp_avg',
    ascending: true,
    pick: (t) => toNum((t.pitching as Record<string, unknown> | null)?.opp_avg as string | number | null | undefined),
    format: fmtRate3,
    percentileBaseline: { p10: 0.260, p90: 0.215 },
  },
];

// ── Shared helpers ─────────────────────────────────────────────────────

export function approxPercentile(
  value: number | null,
  baseline: { p10: number; p90: number } | undefined,
): number | null {
  if (value == null || !baseline) return null;
  const { p10, p90 } = baseline;
  const t = (value - p10) / (p90 - p10);
  return Math.round(Math.max(0, Math.min(1, t)) * 100);
}

export function pickWinner(
  a: number | null,
  b: number | null,
  ascending: boolean | undefined,
): 'a' | 'b' | 'tie' | null {
  if (a == null || b == null) return null;
  if (a === b) return 'tie';
  if (ascending) return a < b ? 'a' : 'b';
  return a > b ? 'a' : 'b';
}
