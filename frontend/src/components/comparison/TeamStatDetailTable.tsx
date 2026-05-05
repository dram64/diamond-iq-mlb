import type { TeamStats } from '@/types/teamStats';

interface TeamRow {
  label: string;
  side: 'hitting' | 'pitching';
  field: string;
  format: (v: number | null) => string;
  ascending?: boolean;
}

const fmtRate3 = (v: number | null): string => {
  if (v == null) return '—';
  return v < 1 ? v.toFixed(3).replace(/^0\./, '.') : v.toFixed(3);
};
const fmtFloat = (decimals: number) => (v: number | null): string =>
  v == null ? '—' : v.toFixed(decimals);
const fmtInt = (v: number | null): string =>
  v == null ? '—' : Math.round(v).toString();

const HITTING_ROWS: TeamRow[] = [
  { label: 'AVG', side: 'hitting', field: 'avg', format: fmtRate3 },
  { label: 'OBP', side: 'hitting', field: 'obp', format: fmtRate3 },
  { label: 'SLG', side: 'hitting', field: 'slg', format: fmtRate3 },
  { label: 'OPS', side: 'hitting', field: 'ops', format: fmtRate3 },
  { label: 'HR', side: 'hitting', field: 'home_runs', format: fmtInt },
  { label: 'RBI', side: 'hitting', field: 'rbi', format: fmtInt },
  { label: 'SB', side: 'hitting', field: 'stolen_bases', format: fmtInt },
];

const PITCHING_ROWS: TeamRow[] = [
  { label: 'ERA', side: 'pitching', field: 'era', format: fmtFloat(2), ascending: true },
  { label: 'WHIP', side: 'pitching', field: 'whip', format: fmtFloat(2), ascending: true },
  { label: 'K', side: 'pitching', field: 'strikeouts', format: fmtInt },
  { label: 'W', side: 'pitching', field: 'wins', format: fmtInt },
  { label: 'SV', side: 'pitching', field: 'saves', format: fmtInt },
  { label: 'OPP AVG', side: 'pitching', field: 'opp_avg', format: fmtRate3, ascending: true },
];

function pick(team: TeamStats, side: 'hitting' | 'pitching', field: string): number | null {
  const block = (side === 'hitting' ? team.hitting : team.pitching) as
    | Record<string, unknown>
    | null;
  if (!block) return null;
  const v = block[field];
  if (v == null || v === '') return null;
  if (typeof v === 'number') return Number.isFinite(v) ? v : null;
  const n = Number.parseFloat(String(v));
  return Number.isFinite(n) ? n : null;
}

function pickWinner(
  a: number | null,
  b: number | null,
  ascending: boolean | undefined,
): 'a' | 'b' | 'tie' | null {
  if (a == null || b == null) return null;
  if (a === b) return 'tie';
  if (ascending) return a < b ? 'a' : 'b';
  return a > b ? 'a' : 'b';
}

interface TeamStatDetailTableProps {
  teams: readonly TeamStats[];
}

export function TeamStatDetailTable({ teams }: TeamStatDetailTableProps) {
  if (teams.length < 2) return null;
  return (
    <div className="rounded-l border border-hairline-strong bg-surface-elevated p-5 shadow-sm">
      <div className="kicker mb-3 text-accent-leather">Numerical detail</div>
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <Group title="Team batting" rows={HITTING_ROWS} teams={teams} />
        <Group title="Team pitching" rows={PITCHING_ROWS} teams={teams} />
      </div>
    </div>
  );
}

function Group({
  title,
  rows,
  teams,
}: {
  title: string;
  rows: TeamRow[];
  teams: readonly TeamStats[];
}) {
  return (
    <div>
      <div className="kicker mb-2 text-paper-ink-soft">{title}</div>
      <div
        className="grid items-baseline gap-x-3 gap-y-1.5"
        style={{
          gridTemplateColumns: `120px repeat(${teams.length}, minmax(0, 1fr))`,
        }}
      >
        <div />
        {teams.map((t) => (
          <div
            key={t.team_id}
            className="truncate text-right text-[11px] font-semibold text-paper-ink-muted"
          >
            {t.team_name}
          </div>
        ))}
        {rows.map((row) => (
          <Row key={row.field} row={row} teams={teams} />
        ))}
      </div>
    </div>
  );
}

function Row({ row, teams }: { row: TeamRow; teams: readonly TeamStats[] }) {
  const values = teams.map((t) => pick(t, row.side, row.field));
  let winnerIdx: number | null = null;
  for (let i = 0; i < values.length; i++) {
    if (values[i] == null) continue;
    if (winnerIdx === null) {
      winnerIdx = i;
      continue;
    }
    const cmp = pickWinner(values[i], values[winnerIdx], row.ascending);
    if (cmp === 'a') winnerIdx = i;
  }
  return (
    <>
      <span className="text-[12.5px] text-paper-ink">{row.label}</span>
      {values.map((v, i) => (
        <span
          key={i}
          className={[
            'mono text-right text-[13px]',
            winnerIdx === i ? 'font-bold text-accent-leather' : 'text-paper-ink-muted',
          ].join(' ')}
        >
          {row.format(v)}
        </span>
      ))}
    </>
  );
}
