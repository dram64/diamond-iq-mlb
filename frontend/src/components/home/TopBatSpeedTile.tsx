import { Link } from 'react-router-dom';

import { PlayerHeadshot } from '@/components/PlayerHeadshot';
import { Skeleton } from '@/components/primitives/Skeleton';
import { useLeaders } from '@/hooks/useLeaders';

export function TopBatSpeedTile() {
  const { data, isLoading, isError } = useLeaders('hitting', 'bat_speed', 1);
  const top = data?.data.leaders[0];
  const value =
    top && typeof top.avg_bat_speed === 'number' ? top.avg_bat_speed.toFixed(1) : null;

  return (
    <section
      aria-label="Top bat speed"
      className="flex flex-col gap-3 rounded-l border border-hairline-strong bg-surface-elevated p-5 shadow-sm"
    >
      <div className="flex items-baseline justify-between border-b border-hairline pb-2">
        <span className="kicker text-accent-leather">Top Bat Speed · 2026</span>
        <span className="kicker text-paper-ink-soft">Season leader</span>
      </div>

      {isLoading && <BatSpeedSkeleton />}
      {isError && <Empty message="Bat-speed leader unavailable." />}
      {!isLoading && !isError && !top && <Empty message="No qualified hitters yet." />}
      {!isLoading && !isError && top && value && (
        <Link
          to={`/compare-players?ids=${top.person_id}`}
          className="group flex items-center gap-3 rounded-m border border-hairline bg-surface-sunken/40 p-3 transition-colors duration-200 hover:bg-surface-sunken/70"
        >
          <PlayerHeadshot
            playerId={top.person_id}
            playerName={top.full_name}
            size="md"
          />
          <div className="min-w-0 flex-1">
            <div className="truncate text-[14px] font-bold text-paper-ink">
              {top.full_name}
            </div>
            <div className="mono text-[10.5px] text-paper-ink-soft">Rank #{top.rank} MLB</div>
          </div>
          <div className="flex items-baseline gap-1.5">
            <span className="display text-[26px] leading-none text-accent-leather">
              {value}
            </span>
            <span className="kicker text-paper-ink-muted">mph</span>
          </div>
        </Link>
      )}
    </section>
  );
}

function BatSpeedSkeleton() {
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
