import {
  compareStatBetter,
  formatStat,
  isAscendingStat,
  parseStatNumber,
} from '@/lib/stats';
import type {
  ComparePlayer,
  StatcastBattedBall,
  StatcastBatTracking,
  StatcastBlock,
  StatcastHitting,
  StatcastPitching,
} from '@/types/compare';

// ── Field group definitions ────────────────────────────────────────────

interface StatcastRow {
  /** Per-stat token used for direction lookup + display formatting. */
  token: string;
  label: string;
  /** Reach into the right sub-block by name. */
  block: 'hitting' | 'pitching' | 'bat_tracking' | 'batted_ball';
  /** Field name within that block. */
  field: string;
  /** Display formatter override — Statcast uses a few stats whose token
   *  doesn't match the player-stats formatter's known set. */
  formatter?: (value: number | string | null | undefined) => string;
  /** True if lower is better (for the bar inversion). */
  ascending?: boolean;
}

const ONE_DECIMAL = (v: number | string | null | undefined): string => {
  if (v == null || v === '') return '—';
  if (typeof v === 'string' && /^[.-]?\d/.test(v)) return v;
  const n = typeof v === 'number' ? v : Number.parseFloat(String(v));
  return Number.isFinite(n) ? n.toFixed(1) : '—';
};
const TWO_DECIMAL = (v: number | string | null | undefined): string => {
  if (v == null || v === '') return '—';
  const n = typeof v === 'number' ? v : Number.parseFloat(String(v));
  return Number.isFinite(n) ? n.toFixed(2) : '—';
};
const PERCENT = ONE_DECIMAL;
const RATE_OF_1 = (v: number | string | null | undefined): string => {
  if (v == null || v === '') return '—';
  const n = typeof v === 'number' ? v : Number.parseFloat(String(v));
  return Number.isFinite(n) ? `${(n * 100).toFixed(1)}%` : '—';
};

const QUALITY_OF_CONTACT_ROWS: StatcastRow[] = [
  { token: 'avg_hit_speed', label: 'Avg EV', block: 'hitting', field: 'avg_hit_speed', formatter: ONE_DECIMAL },
  { token: 'max_hit_speed', label: 'Max EV', block: 'hitting', field: 'max_hit_speed', formatter: ONE_DECIMAL },
  { token: 'barrel_percent', label: 'Barrel %', block: 'hitting', field: 'barrel_percent', formatter: PERCENT },
  { token: 'ev95_percent', label: 'Hard-hit %', block: 'hitting', field: 'ev95_percent', formatter: PERCENT },
  { token: 'sweet_spot_percent', label: 'Sweet spot %', block: 'hitting', field: 'sweet_spot_percent', formatter: PERCENT },
];

const EXPECTED_STATS_ROWS: StatcastRow[] = [
  { token: 'xba', label: 'xBA', block: 'hitting', field: 'xba' },
  { token: 'xslg', label: 'xSLG', block: 'hitting', field: 'xslg' },
  { token: 'xwoba', label: 'xwOBA', block: 'hitting', field: 'xwoba' },
  { token: 'sprint_speed', label: 'Sprint speed', block: 'hitting', field: 'sprint_speed', formatter: ONE_DECIMAL },
];

const BAT_TRACKING_ROWS: StatcastRow[] = [
  { token: 'avg_bat_speed', label: 'Avg bat speed', block: 'bat_tracking', field: 'avg_bat_speed', formatter: ONE_DECIMAL },
  { token: 'swing_length', label: 'Swing length', block: 'bat_tracking', field: 'swing_length', formatter: ONE_DECIMAL },
  { token: 'hard_swing_rate', label: 'Hard-swing %', block: 'bat_tracking', field: 'hard_swing_rate', formatter: RATE_OF_1 },
  { token: 'squared_up_per_swing', label: 'Squared-up/swing', block: 'bat_tracking', field: 'squared_up_per_swing', formatter: RATE_OF_1 },
];

const SPRAY_ROWS: StatcastRow[] = [
  { token: 'pull_rate', label: 'Pull %', block: 'batted_ball', field: 'pull_rate', formatter: RATE_OF_1 },
  { token: 'straight_rate', label: 'Center %', block: 'batted_ball', field: 'straight_rate', formatter: RATE_OF_1 },
  { token: 'oppo_rate', label: 'Oppo %', block: 'batted_ball', field: 'oppo_rate', formatter: RATE_OF_1 },
];

const PITCHER_ROWS: StatcastRow[] = [
  { token: 'fastball_avg_speed', label: 'Fastball velo', block: 'pitching', field: 'fastball_avg_speed', formatter: ONE_DECIMAL },
  { token: 'fastball_avg_spin', label: 'Fastball spin', block: 'pitching', field: 'fastball_avg_spin', formatter: (v) => (v == null || v === '' ? '—' : Number.parseInt(String(v), 10).toString()) },
  { token: 'whiff_percent', label: 'Whiff %', block: 'pitching', field: 'whiff_percent', formatter: PERCENT },
  { token: 'chase_whiff_percent', label: 'Chase whiff %', block: 'pitching', field: 'chase_whiff_percent', formatter: PERCENT },
  { token: 'xera', label: 'xERA', block: 'pitching', field: 'xera', formatter: TWO_DECIMAL, ascending: true },
  { token: 'xba_against', label: 'xBA against', block: 'pitching', field: 'xba_against', ascending: true },
];

// ── Component ──────────────────────────────────────────────────────────

interface StatcastSectionProps {
  players: readonly ComparePlayer[];
}

export function StatcastSection({ players }: StatcastSectionProps) {
  const anyHasStatcast = players.some((p) => p.statcast != null);
  if (!anyHasStatcast) return null;

  const anyHasHitting = players.some((p) => p.statcast?.hitting != null);
  const anyHasPitching = players.some((p) => p.statcast?.pitching != null);
  const anyHasBatTracking = players.some((p) => p.statcast?.bat_tracking != null);
  const anyHasBattedBall = players.some((p) => p.statcast?.batted_ball != null);

  const blocks: { title: string; rows: StatcastRow[] }[] = [];
  if (anyHasHitting) {
    blocks.push({ title: 'Quality of contact', rows: QUALITY_OF_CONTACT_ROWS });
    blocks.push({ title: 'Expected stats', rows: EXPECTED_STATS_ROWS });
  }
  if (anyHasBatTracking) blocks.push({ title: 'Bat tracking', rows: BAT_TRACKING_ROWS });
  if (anyHasBattedBall) blocks.push({ title: 'Spray (pull / center / oppo)', rows: SPRAY_ROWS });
  if (anyHasPitching) blocks.push({ title: 'Pitcher arsenal', rows: PITCHER_ROWS });

  return (
    <section
      aria-label="Statcast comparison"
      className="mt-6 border-t border-hairline-strong pt-5"
    >
      <div className="mb-4 flex items-baseline justify-between">
        <h3 className="text-[15px] font-bold tracking-tight text-paper-2">Statcast</h3>
        <span className="mono text-[10.5px] text-paper-4">via Baseball Savant</span>
      </div>

      <div className="flex flex-col gap-5">
        {blocks.map((b) => (
          <StatcastSubBlock key={b.title} title={b.title} rows={b.rows} players={players} />
        ))}
      </div>

      <div className="mt-5 border-t border-hairline pt-3 text-[11px] italic text-paper-4">
        Bat tracking metrics available from 2024+. Statcast data via Baseball Savant.
        Players outside the qualified pool may show no data.
      </div>
    </section>
  );
}

interface StatcastSubBlockProps {
  title: string;
  rows: StatcastRow[];
  players: readonly ComparePlayer[];
}

function StatcastSubBlock({ title, rows, players }: StatcastSubBlockProps) {
  return (
    <div>
      <div className="kicker mb-2 text-paper-4">{title}</div>
      <div className="flex flex-col gap-2.5">
        {rows.map((row) => (
          <StatcastRowView key={row.token} row={row} players={players} />
        ))}
      </div>
    </div>
  );
}

function _resolveValue(
  player: ComparePlayer,
  row: StatcastRow,
): number | string | null | undefined {
  const sc: StatcastBlock | null | undefined = player.statcast;
  if (!sc) return null;
  const block:
    | StatcastHitting
    | StatcastPitching
    | StatcastBatTracking
    | StatcastBattedBall
    | null = sc[row.block];
  if (!block) return null;
  return (block as Record<string, unknown>)[row.field] as
    | number
    | string
    | null
    | undefined;
}

interface StatcastRowViewProps {
  row: StatcastRow;
  players: readonly ComparePlayer[];
}

function StatcastRowView({ row, players }: StatcastRowViewProps) {
  const ascending = row.ascending ?? isAscendingStat(row.token);

  const numericValues: number[] = [];
  for (const p of players) {
    const v = parseStatNumber(_resolveValue(p, row));
    if (v !== null) numericValues.push(v);
  }
  const max = numericValues.length > 0 ? Math.max(...numericValues) * 1.05 || 1 : 1;

  // Pick the winner across the row (skip players with null values).
  let winnerIdx: number | null = null;
  for (let i = 0; i < players.length; i++) {
    const v = _resolveValue(players[i], row);
    if (v == null || v === '') continue;
    if (winnerIdx === null) {
      winnerIdx = i;
      continue;
    }
    const prev = _resolveValue(players[winnerIdx], row);
    // For ascending stats, the row.ascending flag overrides
    // compareStatBetter's token lookup (which won't know about Statcast-
    // specific tokens like xera). Fall back to direct numeric compare.
    if (row.ascending) {
      const a = parseStatNumber(v);
      const b = parseStatNumber(prev);
      if (a !== null && b !== null && a < b) winnerIdx = i;
      continue;
    }
    const cmp = compareStatBetter(row.token, v, prev);
    if (cmp === 'a') winnerIdx = i;
  }

  return (
    <div
      className="grid items-center gap-3"
      style={{ gridTemplateColumns: `92px repeat(${players.length}, minmax(0, 1fr))` }}
    >
      <span className="kicker text-[10.5px] text-paper-4">{row.label}</span>
      {players.map((p, i) => {
        const value = _resolveValue(p, row);
        const num = parseStatNumber(value);
        const fill =
          num !== null
            ? ascending
              ? Math.max(0, max - num) / max
              : num / max
            : 0;
        const isWinner = winnerIdx === i;
        const display = row.formatter
          ? row.formatter(value ?? null)
          : formatStat(row.token, (value as number | string | null | undefined) ?? null);
        return (
          <div key={p.person_id} className="flex items-center gap-2">
            <div className="relative h-2 flex-1 overflow-hidden rounded-s bg-surface-3">
              <div
                className={[
                  'h-full transition-[width] duration-300',
                  isWinner ? 'bg-accent' : 'bg-paper-5',
                ].join(' ')}
                style={{ width: `${fill * 100}%` }}
              />
            </div>
            <span
              className={[
                'mono w-[64px] shrink-0 text-right text-[12.5px]',
                isWinner ? 'font-bold text-accent' : 'font-medium text-paper-3',
              ].join(' ')}
            >
              {display}
            </span>
          </div>
        );
      })}
    </div>
  );
}
