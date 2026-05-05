import { useMemo } from 'react';
import { Link, useSearchParams } from 'react-router-dom';

import { ErrorBanner } from '@/components/primitives/ErrorBanner';
import { Skeleton } from '@/components/primitives/Skeleton';
import { PlayerHeadshot } from '@/components/PlayerHeadshot';
import { useLeaders } from '@/hooks/useLeaders';
import { getMlbTeam } from '@/lib/mlbTeams';
import { formatStat, statStorageField } from '@/lib/stats';
import type { LeaderGroup } from '@/types/leaders';

interface StatOption {
  group: LeaderGroup;
  token: string;
  label: string;
  description: string;
}

const STAT_CATALOG: readonly StatOption[] = [
  // Hitting
  { group: 'hitting', token: 'woba', label: 'wOBA', description: 'Weighted on-base avg' },
  { group: 'hitting', token: 'ops_plus', label: 'OPS+', description: 'Park-adjusted OPS index' },
  { group: 'hitting', token: 'hr', label: 'HR', description: 'Home runs' },
  { group: 'hitting', token: 'rbi', label: 'RBI', description: 'Runs batted in' },
  { group: 'hitting', token: 'avg', label: 'AVG', description: 'Batting average' },
  { group: 'hitting', token: 'ops', label: 'OPS', description: 'On-base + slugging' },
  // Pitching
  { group: 'pitching', token: 'era', label: 'ERA', description: 'Earned-run average (lower better)' },
  { group: 'pitching', token: 'fip', label: 'FIP', description: 'Fielding-independent pitching' },
  { group: 'pitching', token: 'whip', label: 'WHIP', description: 'Walks + hits per IP (lower better)' },
  { group: 'pitching', token: 'k', label: 'K', description: 'Strikeouts' },
  { group: 'pitching', token: 'wins', label: 'W', description: 'Wins' },
  { group: 'pitching', token: 'saves', label: 'SV', description: 'Saves' },
];

const DEFAULT_GROUP: LeaderGroup = 'hitting';
const DEFAULT_STAT = 'woba';
const TOP_N = 50;
const TOP_HIGHLIGHT = 5; // First N rows render their value in leather-bold.

export function StatsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const groupParam = searchParams.get('group');
  const statParam = searchParams.get('stat');

  const active = useMemo<StatOption>(() => {
    const found = STAT_CATALOG.find(
      (s) => s.group === groupParam && s.token === statParam,
    );
    return (
      found ??
      STAT_CATALOG.find((s) => s.group === DEFAULT_GROUP && s.token === DEFAULT_STAT)!
    );
  }, [groupParam, statParam]);

  const leaders = useLeaders(active.group, active.token, TOP_N);

  function pick(s: StatOption) {
    setSearchParams({ group: s.group, stat: s.token });
  }

  return (
    <section className="page-data">
      <div className="kicker mb-2 text-accent-leather">Stats</div>
      <h1 className="display text-h1 text-paper-ink">Stat Explorer</h1>
      <p className="mt-1 max-w-2xl text-[13px] text-paper-ink-muted">
        Top {TOP_N} qualified leaders for the selected stat, refreshed daily.
      </p>

      <div className="mt-7 flex flex-col gap-3">
        <ChipRow
          label="Hitting"
          options={STAT_CATALOG.filter((s) => s.group === 'hitting')}
          active={active}
          onPick={pick}
        />
        <ChipRow
          label="Pitching"
          options={STAT_CATALOG.filter((s) => s.group === 'pitching')}
          active={active}
          onPick={pick}
        />
      </div>

      <div className="mt-8">
        <div className="mb-5">
          <span className="kicker text-accent-leather">{active.group}</span>
          <h2 className="display mt-1 text-[28px] leading-tight text-paper-ink">
            {active.label}
          </h2>
          <p className="mt-1 text-[13px] text-paper-ink-muted">
            Top {TOP_N} by {active.label} · {active.description} · 2026
          </p>
        </div>

        <div className="rounded-l border border-hairline-strong bg-surface-elevated shadow-sm">
          {leaders.isLoading ? (
            <LeaderSkeleton />
          ) : leaders.isError ? (
            <div className="p-5">
              <ErrorBanner
                title="Couldn't load leaderboard"
                message={leaders.error?.message ?? 'Try again shortly.'}
                onRetry={() => void leaders.refetch()}
              />
            </div>
          ) : (
            <LeaderTable
              rows={leaders.data?.data.leaders ?? []}
              statToken={active.token}
              statLabel={active.label}
            />
          )}
        </div>
      </div>
    </section>
  );
}

interface ChipRowProps {
  label: string;
  options: readonly StatOption[];
  active: StatOption;
  onPick: (s: StatOption) => void;
}

function ChipRow({ label, options, active, onPick }: ChipRowProps) {
  return (
    <div className="flex items-center gap-3">
      <span className="kicker w-[68px] shrink-0 text-paper-ink-soft">{label}</span>
      <div
        className="relative flex-1 overflow-hidden"
        // Edge gradient masks signal scrollability on overflow.
        style={{
          maskImage:
            'linear-gradient(to right, transparent 0, black 16px, black calc(100% - 16px), transparent 100%)',
          WebkitMaskImage:
            'linear-gradient(to right, transparent 0, black 16px, black calc(100% - 16px), transparent 100%)',
        }}
      >
        <div
          className="flex gap-2 overflow-x-auto px-4 py-1"
          style={{ scrollbarWidth: 'none' }}
        >
          {options.map((s) => {
            const isActive = active.group === s.group && active.token === s.token;
            return (
              <button
                key={s.token}
                type="button"
                aria-pressed={isActive}
                onClick={() => onPick(s)}
                className={[
                  'whitespace-nowrap rounded-m border px-4 py-1.5 text-[12.5px] font-bold tracking-tight transition-colors duration-200 ease-out',
                  isActive
                    ? 'border-accent-leather bg-accent-leather/15 text-accent-leather shadow-sm'
                    : 'border-hairline bg-surface-elevated text-paper-ink-muted hover:border-accent-leather/40 hover:text-paper-ink',
                ].join(' ')}
              >
                {s.label}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

interface LeaderTableProps {
  rows: ReadonlyArray<{
    person_id: number;
    full_name: string;
    team_id?: number;
    rank: number;
    [key: string]: unknown;
  }>;
  statToken: string;
  statLabel: string;
}

function LeaderTable({ rows, statToken, statLabel }: LeaderTableProps) {
  if (rows.length === 0) {
    return (
      <div className="px-2 py-12 text-center text-[13px] text-paper-ink-soft">
        No qualified leaders for this stat yet.
      </div>
    );
  }
  const storageField = statStorageField(statToken);

  return (
    <div className="overflow-hidden">
      {/* Header */}
      <div className="grid grid-cols-[44px_1fr_72px_100px] items-center gap-3 border-b border-hairline-strong bg-surface-sunken/40 px-4 py-2.5 text-[10.5px] font-bold uppercase tracking-[0.06em] text-paper-ink-soft sm:grid-cols-[44px_1fr_120px_100px]">
        <span>Rank</span>
        <span>Player</span>
        <span className="hidden sm:inline">Team</span>
        <span className="text-right">{statLabel}</span>
      </div>
      {/* Body — alternating tint via odd:bg-... */}
      <ul className="flex flex-col">
        {rows.map((r) => {
          const team = r.team_id != null ? getMlbTeam(r.team_id) : undefined;
          const value = r[storageField] ?? r[statToken];
          const topFive = r.rank <= TOP_HIGHLIGHT;
          return (
            <li key={r.person_id}>
              <Link
                to={`/compare-players?ids=${r.person_id}`}
                className="group grid grid-cols-[44px_1fr_72px_100px] items-center gap-3 border-b border-hairline px-4 py-2.5 text-[13px] transition-colors duration-200 ease-out odd:bg-surface-sunken/25 hover:bg-surface-elevated-hover sm:grid-cols-[44px_1fr_120px_100px]"
              >
                <span
                  className={[
                    'mono text-[12.5px]',
                    topFive ? 'font-bold text-accent-leather' : 'text-paper-ink-soft',
                  ].join(' ')}
                >
                  #{r.rank}
                </span>
                <div className="flex min-w-0 items-center gap-2.5">
                  <PlayerHeadshot playerId={r.person_id} playerName={r.full_name} size="sm" />
                  <span className="truncate font-semibold text-paper-ink group-hover:text-accent-leather">
                    {r.full_name}
                  </span>
                </div>
                <div className="hidden items-center gap-2 sm:flex">
                  {team ? (
                    <>
                      <img
                        src={team.logoPath}
                        alt=""
                        width={16}
                        height={16}
                        className="h-4 w-4 shrink-0"
                      />
                      <span className="mono text-[11px] text-paper-ink-soft">
                        {team.abbreviation}
                      </span>
                    </>
                  ) : (
                    <span className="mono text-[11px] text-paper-ink-soft">—</span>
                  )}
                </div>
                <span
                  className={[
                    'mono text-right text-[14px]',
                    topFive ? 'font-bold text-accent-leather' : 'font-semibold text-paper-ink',
                  ].join(' ')}
                >
                  {formatStat(statToken, (value as number | string | null | undefined) ?? null)}
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function LeaderSkeleton() {
  return (
    <div className="flex flex-col">
      <div className="grid grid-cols-[44px_1fr_72px_100px] items-center gap-3 border-b border-hairline-strong bg-surface-sunken/40 px-4 py-2.5 sm:grid-cols-[44px_1fr_120px_100px]">
        <Skeleton className="h-3 w-8" />
        <Skeleton className="h-3 w-16" />
        <Skeleton className="hidden h-3 w-12 sm:block" />
        <Skeleton className="ml-auto h-3 w-12" />
      </div>
      {Array.from({ length: 10 }).map((_, i) => (
        <div
          key={i}
          className="grid grid-cols-[44px_1fr_72px_100px] items-center gap-3 border-b border-hairline px-4 py-2.5 sm:grid-cols-[44px_1fr_120px_100px]"
        >
          <Skeleton className="h-3 w-6" />
          <div className="flex items-center gap-2.5">
            <Skeleton className="h-8 w-8 rounded-full" />
            <Skeleton className="h-4 w-32" />
          </div>
          <Skeleton className="hidden h-3 w-12 sm:block" />
          <Skeleton className="ml-auto h-4 w-12" />
        </div>
      ))}
    </div>
  );
}
