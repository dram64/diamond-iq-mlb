import { Card } from '@/components/primitives/Card';
import { PlayerHeadshot } from '@/components/PlayerHeadshot';
import { Skeleton } from '@/components/primitives/Skeleton';
import { useLeaders } from '@/hooks/useLeaders';
import { formatStat, statStorageField } from '@/lib/stats';
import type { LeaderGroup, LeaderRecord } from '@/types/leaders';
import { Link } from 'react-router-dom';

const ROWS = 5;

interface LeadersListProps {
  title: string;
  group: LeaderGroup;
  /** First column drives the row order; subsequent columns are looked up
   *  on the same player record returned by the primary query. */
  primaryStat: string;
  secondaryStats: readonly string[];
  /** Column header labels, in order: [name spacer, primary, ...secondary]. */
  cols: readonly string[];
  linkTo: string;
}

export function LeadersList({
  title,
  group,
  primaryStat,
  secondaryStats,
  cols,
  linkTo,
}: LeadersListProps) {
  const primary = useLeaders(group, primaryStat, ROWS);
  const isLoading = primary.isLoading;
  const isError = primary.isError;
  const leaders = primary.data?.data.leaders ?? [];
  // The API echoes the storage attribute name (e.g. URL "hr" → stored
  // "home_runs"). Read row values by storage name; fall back to URL token
  // for stats where they match (avg, era, etc.).
  const primaryField = primary.data?.data.field ?? primaryStat;

  const totalCols = 1 + 1 + secondaryStats.length; // rank + name + stats
  const gridColsClass =
    totalCols === 5
      ? 'grid-cols-[22px_1fr_44px_36px_40px_40px]'
      : totalCols === 6
        ? 'grid-cols-[22px_1fr_44px_36px_40px_40px_40px]'
        : 'grid-cols-[22px_1fr_44px_44px_44px]';

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
      </div>
      <div>
        {isLoading ? (
          <LeadersSkeleton rows={ROWS} totalCols={totalCols} gridColsClass={gridColsClass} />
        ) : isError ? (
          <ErrorState onRetry={() => void primary.refetch()} />
        ) : leaders.length === 0 ? (
          <EmptyState />
        ) : (
          leaders.map((row) => (
            <LeaderListRow
              key={row.person_id}
              row={row}
              primaryStat={primaryStat}
              primaryField={primaryField}
              secondaryStats={secondaryStats}
              gridColsClass={gridColsClass}
            />
          ))
        )}
      </div>
    </Card>
  );
}

interface LeaderListRowProps {
  row: LeaderRecord;
  primaryStat: string;
  primaryField: string;
  secondaryStats: readonly string[];
  gridColsClass: string;
}

function LeaderListRow({
  row,
  primaryStat,
  primaryField,
  secondaryStats,
  gridColsClass,
}: LeaderListRowProps) {
  return (
    <div
      className={[
        'grid items-center gap-2 border-b border-hairline px-4 py-2.5 last:border-b-0',
        gridColsClass,
      ].join(' ')}
    >
      <span className="mono text-[11px] text-paper-4">{row.rank}</span>
      <div className="flex min-w-0 items-center gap-2">
        <PlayerHeadshot playerId={row.person_id} playerName={row.full_name} size="sm" />
        <span className="truncate text-[12.5px] font-medium text-paper">{row.full_name}</span>
      </div>
      <span className="mono text-right text-[12px] font-bold text-accent">
        {formatStat(primaryStat, row[primaryField] as number | string | undefined)}
      </span>
      {secondaryStats.map((s) => (
        <span key={s} className="mono text-right text-[12px] font-medium text-paper-2">
          {formatStat(s, row[statStorageField(s)] as number | string | undefined)}
        </span>
      ))}
    </div>
  );
}

interface LeadersSkeletonProps {
  rows: number;
  totalCols: number;
  gridColsClass: string;
}

function LeadersSkeleton({ rows, totalCols, gridColsClass }: LeadersSkeletonProps) {
  return (
    <>
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          className={[
            'grid items-center gap-2 border-b border-hairline px-4 py-2.5 last:border-b-0',
            gridColsClass,
          ].join(' ')}
          aria-hidden="true"
        >
          <Skeleton className="h-3 w-4" />
          <div className="flex items-center gap-2">
            <Skeleton className="h-4 w-4 rounded" />
            <Skeleton className="h-3 w-24" />
          </div>
          {Array.from({ length: totalCols - 2 }).map((_, j) => (
            <Skeleton key={j} className="ml-auto h-3 w-8" />
          ))}
        </div>
      ))}
    </>
  );
}

function EmptyState() {
  return (
    <div className="px-4 py-6 text-center text-[12px] text-paper-4">
      No leaders available yet
    </div>
  );
}

function ErrorState({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="px-4 py-6 text-center text-[12px] text-paper-4">
      Couldn't load leaders.{' '}
      <button
        type="button"
        onClick={onRetry}
        className="text-accent underline hover:text-accent-glow"
      >
        Retry
      </button>
    </div>
  );
}
