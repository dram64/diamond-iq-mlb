import { Link } from 'react-router-dom';

import { PlayerHeadshot } from '@/components/PlayerHeadshot';
import { Skeleton } from '@/components/primitives/Skeleton';
import { useLeaders } from '@/hooks/useLeaders';
import type { LeaderGroup } from '@/types/leaders';

interface MetricSpec {
  /** URL token passed to /api/leaders/{group}/{stat}. */
  token: string;
  /** Hitting or pitching — selects the leaders allowlist branch. */
  group: LeaderGroup;
  /** Display label for the leather kicker. */
  label: string;
  /** Stored value attribute key on the response row. */
  field: string;
  /** Format the leader's value for display. */
  format: (v: number) => string;
}

const METRICS_BY_DOW: readonly MetricSpec[] = [
  // Sunday (0)
  {
    token: 'sprint_speed',
    group: 'hitting',
    label: 'Top Sprint Speed',
    field: 'sprint_speed',
    format: (v) => `${v.toFixed(1)} ft/s`,
  },
  // Monday
  {
    token: 'max_hit_speed',
    group: 'hitting',
    label: 'Peak Exit Velocity',
    field: 'max_hit_speed',
    format: (v) => `${v.toFixed(1)} mph`,
  },
  // Tuesday
  {
    token: 'barrel_percent',
    group: 'hitting',
    label: 'Top Barrel Rate',
    field: 'barrel_percent',
    format: (v) => `${v.toFixed(1)}%`,
  },
  // Wednesday
  {
    token: 'fastball_avg_speed',
    group: 'pitching',
    label: 'Top Fastball Velo',
    field: 'fastball_avg_speed',
    format: (v) => `${v.toFixed(1)} mph`,
  },
  // Thursday
  {
    token: 'xwoba',
    group: 'hitting',
    label: 'Top xwOBA',
    field: 'xwoba',
    format: (v) => v.toFixed(3).replace(/^0\./, '.'),
  },
  // Friday
  {
    token: 'whiff_percent',
    group: 'pitching',
    label: 'Top Whiff %',
    field: 'whiff_percent',
    format: (v) => `${v.toFixed(1)}%`,
  },
  // Saturday
  {
    token: 'xera',
    group: 'pitching',
    label: 'Best xERA',
    field: 'xera',
    format: (v) => v.toFixed(2),
  },
];

const DOW_NAMES = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'] as const;

export function StatcastLeaderOfWeekTile() {
  const dow = new Date().getDay(); // 0..6
  const metric = METRICS_BY_DOW[dow] ?? METRICS_BY_DOW[0];
  const dayName = DOW_NAMES[dow] ?? 'Today';

  const { data, isLoading, isError } = useLeaders(metric.group, metric.token, 1);
  const top = data?.data.leaders[0];
  const rawValue = top ? (top[metric.field] as number | string | undefined) : undefined;
  const numericValue = typeof rawValue === 'number' ? rawValue : Number.parseFloat(String(rawValue ?? ''));
  const valueLabel = Number.isFinite(numericValue) ? metric.format(numericValue) : null;

  return (
    <section
      aria-label="Statcast leader of the week"
      className="flex flex-col gap-3 rounded-l border border-hairline-strong bg-surface-elevated p-5 shadow-sm"
    >
      <div className="flex items-baseline justify-between border-b border-hairline pb-2">
        <span className="kicker text-accent-leather">{metric.label}</span>
        <span className="kicker text-paper-ink-soft">{dayName} · daily rotation</span>
      </div>

      {isLoading && <TileSkeleton />}
      {isError && <Empty message="Leader unavailable." />}
      {!isLoading && !isError && !top && <Empty message="No qualified players yet." />}
      {!isLoading && !isError && top && valueLabel && (
        <Link
          to={`/compare-players?ids=${top.person_id}`}
          className="group flex items-center gap-3 rounded-m border border-hairline bg-surface-sunken/40 p-3 transition-colors duration-200 hover:bg-surface-sunken/70"
        >
          <PlayerHeadshot playerId={top.person_id} playerName={top.full_name} size="md" />
          <div className="min-w-0 flex-1">
            <div className="truncate text-[14px] font-bold text-paper-ink">{top.full_name}</div>
            <div className="mono text-[10.5px] text-paper-ink-soft">Rank #{top.rank} MLB</div>
          </div>
          <div className="display text-[22px] leading-none text-accent-leather">
            {valueLabel}
          </div>
        </Link>
      )}
    </section>
  );
}

function TileSkeleton() {
  return (
    <div className="flex items-center gap-3 rounded-m border border-hairline bg-surface-sunken/40 p-3">
      <Skeleton className="h-12 w-12 rounded-full" />
      <div className="flex flex-1 flex-col gap-1.5">
        <Skeleton className="h-3 w-2/3" />
        <Skeleton className="h-2.5 w-1/3" />
      </div>
      <Skeleton className="h-6 w-16" />
    </div>
  );
}

function Empty({ message }: { message: string }) {
  return (
    <div className="rounded-s border border-dashed border-hairline px-3 py-5 text-center text-[11.5px] text-paper-ink-soft">
      {message}
    </div>
  );
}
