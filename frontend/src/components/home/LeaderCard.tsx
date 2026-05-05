import { Link } from 'react-router-dom';
import type { ReactNode } from 'react';
import { Card } from '@/components/primitives/Card';
import { TeamChip } from '@/components/primitives/TeamChip';
import { teamBy } from '@/mocks/teams';
import type { StandingsRow, TeamId } from '@/types';

function chipFor(id: TeamId, size: number) {
  const t = teamBy(id);
  return <TeamChip abbr={t.abbr} color={t.color} size={size} />;
}

interface LeaderCardProps {
  title: string;
  cols: readonly string[];
  linkTo: string;
  children: ReactNode;
}

export function LeaderCard({ title, cols, linkTo, children }: LeaderCardProps) {
  // Written out so Tailwind's JIT scanner sees each full class name.
  const gridColsClass =
    cols.length === 5
      ? 'grid-cols-[22px_1fr_44px_36px_40px_40px]'
      : 'grid-cols-[22px_1fr_52px_42px_58px]';

  return (
    <Card flush className="overflow-hidden">
      <div className="flex items-center justify-between border-b border-hairline-strong px-4 py-3">
        <h4>{title}</h4>
        <Link
          to={linkTo}
          className="text-[11px] font-semibold text-accent hover:text-accent-glow"
        >
          View all →
        </Link>
      </div>
      <div
        className={[
          'grid items-center gap-2 border-b border-hairline bg-surface-2 px-4 py-2',
          gridColsClass,
        ].join(' ')}
      >
        {cols.map((c, i) => (
          <span
            key={i}
            className={[
              'text-[9.5px] font-bold uppercase tracking-[0.06em] text-paper-4',
              i < 2 ? 'text-left' : 'text-right',
            ].join(' ')}
          >
            {c}
          </span>
        ))}
        {cols.length === 5 && <span />}
      </div>
      <div>{children}</div>
    </Card>
  );
}

interface LeaderRowProps {
  rank: number;
  name: string;
  team: TeamId;
  /** Right-aligned stat cells. Length must equal the card's non-rank/name columns. */
  values: readonly (string | number)[];
  /** Whether each value should be rendered in accent color (same length as `values`). */
  highlight?: readonly boolean[];
}

export function LeaderRow({
  rank,
  name,
  team,
  values,
  highlight = [],
}: LeaderRowProps) {
  return (
    <div className="grid grid-cols-[22px_1fr_44px_36px_40px_40px] items-center gap-2 border-b border-hairline px-4 py-2.5 last:border-b-0">
      <span className="mono text-[11px] text-paper-4">{rank}</span>
      <div className="flex min-w-0 items-center gap-2">
        {chipFor(team, 16)}
        <span className="truncate text-[12.5px] font-medium text-paper">{name}</span>
      </div>
      {values.map((v, i) => (
        <span
          key={i}
          className={[
            'mono text-right text-[12px]',
            highlight[i] ? 'font-bold text-accent' : 'font-medium text-paper-2',
          ].join(' ')}
        >
          {v}
        </span>
      ))}
    </div>
  );
}

interface StandingsTableRowProps {
  rank: number;
  row: StandingsRow;
}

export function StandingsTableRow({ rank, row }: StandingsTableRowProps) {
  const t = teamBy(row.team);
  const rdPositive = row.rd.startsWith('+');
  return (
    <div className="grid grid-cols-[22px_1fr_52px_42px_58px] items-center gap-2 border-b border-hairline px-4 py-2.5 last:border-b-0">
      <span className="mono text-[11px] text-paper-4">{rank}</span>
      <div className="flex min-w-0 items-center gap-2">
        {chipFor(t.id, 16)}
        <span className="text-[12.5px] text-paper">{t.city}</span>
      </div>
      <span className="mono text-right text-[12px] text-paper-2">{row.rec}</span>
      <span className="mono text-right text-[12px] text-paper-4">{row.gb}</span>
      <span
        className={[
          'mono text-right text-[12px]',
          rdPositive ? 'text-good' : 'text-bad',
        ].join(' ')}
      >
        {row.rd}
      </span>
    </div>
  );
}
