import { Card } from '@/components/primitives/Card';
import { PlayerHeadshot } from '@/components/PlayerHeadshot';
import { Skeleton } from '@/components/primitives/Skeleton';
import { useHardestHit } from '@/hooks/useHardestHit';
import { yesterdayUtcDate } from '@/lib/dateUtils';
import type { HardestHitRecord } from '@/types/hardestHit';

const ROWS = 8;
const MIN_FLOOR_MPH = 100;

interface HardestHitChartProps {
  /** YYYY-MM-DD; defaults to yesterday UTC. */
  date?: string;
}

export function HardestHitChart({ date = yesterdayUtcDate() }: HardestHitChartProps) {
  const { data, isLoading, isError, error, refetch } = useHardestHit(date, ROWS);

  if (isLoading) {
    return <HardestHitSkeleton />;
  }

  // Treat the 503 "data_not_yet_available" path as a friendly empty state,
  // not an error retry surface. Anything else is a real failure.
  if (isError && error?.status !== 503) {
    return (
      <Card>
        <div className="px-2 py-6 text-center text-[12px] text-paper-4">
          Couldn't load hardest-hit balls.{' '}
          <button
            type="button"
            onClick={() => void refetch()}
            className="text-accent underline hover:text-accent-glow"
          >
            Retry
          </button>
        </div>
      </Card>
    );
  }

  const hits = data?.data.hits ?? [];
  if (hits.length === 0) {
    return (
      <Card>
        <div className="px-2 py-6 text-center text-[12px] text-paper-4">
          No hardest-hit data for {date} yet.
        </div>
      </Card>
    );
  }

  const max = Math.max(...hits.map((h) => h.launch_speed));
  const min = Math.min(MIN_FLOOR_MPH, ...hits.map((h) => h.launch_speed));
  const range = max - min || 1;

  return (
    <Card>
      <div className="mb-2.5 grid grid-cols-[160px_1fr_90px_70px] items-center gap-3 border-b border-hairline-strong pb-2.5">
        <span className="kicker text-[9px]">Hitter</span>
        <span className="kicker text-[9px]">Exit velocity (mph)</span>
        <span className="kicker text-right text-[9px]">Result</span>
        <span className="kicker text-right text-[9px]">MPH</span>
      </div>
      {hits.map((hit, i) => (
        <HardestHitRow key={`${hit.batter_id}-${hit.game_pk}`} hit={hit} idx={i} min={min} range={range} total={hits.length} />
      ))}
    </Card>
  );
}

interface HardestHitRowProps {
  hit: HardestHitRecord;
  idx: number;
  min: number;
  range: number;
  total: number;
}

function HardestHitRow({ hit, idx, min, range, total }: HardestHitRowProps) {
  const pct = ((hit.launch_speed - min) / range) * 100;
  const opacity = 0.35 + 0.65 * (1 - idx / total);
  return (
    <div className="grid grid-cols-[160px_1fr_90px_70px] items-center gap-3 border-b border-hairline py-2.5 last:border-b-0">
      <div className="flex min-w-0 items-center gap-2">
        <PlayerHeadshot playerId={hit.batter_id} playerName={hit.batter_name} size="sm" />
        <span className="truncate text-[13px] font-medium text-paper">{hit.batter_name}</span>
      </div>
      <div className="relative h-4 overflow-hidden rounded-s bg-surface-3">
        <div
          className={[
            'h-full transition-[width] duration-300',
            idx === 0 ? 'bg-accent' : 'bg-accent-glow',
          ].join(' ')}
          style={{ width: `${pct}%`, opacity }}
        />
      </div>
      <span className="text-right text-[11px] text-paper-4">{hit.result_event ?? '—'}</span>
      <span className="mono text-right text-[13px] font-semibold text-paper">
        {hit.launch_speed.toFixed(1)}
      </span>
    </div>
  );
}

function HardestHitSkeleton() {
  return (
    <Card>
      <div className="mb-2.5 grid grid-cols-[160px_1fr_90px_70px] items-center gap-3 border-b border-hairline-strong pb-2.5">
        <span className="kicker text-[9px]">Hitter</span>
        <span className="kicker text-[9px]">Exit velocity (mph)</span>
        <span className="kicker text-right text-[9px]">Result</span>
        <span className="kicker text-right text-[9px]">MPH</span>
      </div>
      {Array.from({ length: ROWS }).map((_, i) => (
        <div
          key={i}
          className="grid grid-cols-[160px_1fr_90px_70px] items-center gap-3 border-b border-hairline py-2.5 last:border-b-0"
          aria-hidden="true"
        >
          <div className="flex items-center gap-2">
            <Skeleton className="h-[18px] w-[18px] rounded" />
            <Skeleton className="h-3 w-28" />
          </div>
          <Skeleton className="h-4 w-full" />
          <Skeleton className="ml-auto h-3 w-14" />
          <Skeleton className="ml-auto h-3 w-10" />
        </div>
      ))}
    </Card>
  );
}
