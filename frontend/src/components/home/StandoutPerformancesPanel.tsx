import { Link } from 'react-router-dom';

import { PlayerHeadshot } from '@/components/PlayerHeadshot';
import { Skeleton } from '@/components/primitives/Skeleton';
import { useHardestHit } from '@/hooks/useHardestHit';
import { useLeaders } from '@/hooks/useLeaders';
import { yesterdayUtcDate } from '@/lib/dateUtils';

const LEADERS_LIMIT = 3;

export function StandoutPerformancesPanel() {
  return (
    <section
      aria-label="Today's standout performances"
      className="rounded-l border border-hairline-strong bg-surface-elevated p-6 shadow-sm"
    >
      <div className="mb-5 flex items-baseline justify-between border-b border-hairline pb-3">
        <h2 className="text-[18px] font-bold tracking-[-0.005em] text-paper-ink">
          Today's Standout Performances
        </h2>
        <span className="kicker text-paper-ink-soft">Live data</span>
      </div>

      <div className="grid grid-cols-1 gap-5 md:grid-cols-3">
        <HardestHitTile />
        <TopKTile />
        <WobaLeadersTile />
      </div>
    </section>
  );
}

function HardestHitTile() {
  const date = yesterdayUtcDate();
  const { data, isLoading, isError, error } = useHardestHit(date, 1);

  return (
    <Tile kicker="Hardest Hit" rangeNote={`Yesterday · ${date}`} linkTo="/stats">
      {isLoading && <TileSkeleton />}
      {isError && error?.status !== 503 && (
        <TileEmpty message="Couldn't load hardest-hit data." />
      )}
      {!isLoading && !isError && (
        <HitContent
          rows={
            data?.data.hits.slice(0, 1).map((h) => ({
              playerId: h.batter_id,
              fullName: h.batter_name,
              valueLabel: `${h.launch_speed.toFixed(1)} mph`,
              context: h.result_event ?? '—',
            })) ?? []
          }
        />
      )}
    </Tile>
  );
}

function TopKTile() {
  const { data, isLoading, isError, refetch } = useLeaders('pitching', 'k', 1);
  const row = data?.data.leaders[0];
  const value = row?.strikeouts;

  return (
    <Tile kicker="Top Strikeouts" rangeNote="Season K leader" linkTo="/stats">
      {isLoading && <TileSkeleton />}
      {isError && (
        <TileEmpty
          message="Strikeout board unavailable."
          onRetry={() => void refetch()}
        />
      )}
      {!isLoading && !isError && row && (
        <HitContent
          rows={[
            {
              playerId: row.person_id,
              fullName: row.full_name,
              valueLabel: typeof value === 'number' ? `${value} K` : '—',
              context: `Rank #${row.rank} MLB`,
            },
          ]}
        />
      )}
      {!isLoading && !isError && !row && <TileEmpty message="No qualified pitchers yet." />}
    </Tile>
  );
}

function WobaLeadersTile() {
  const { data, isLoading, isError, refetch } = useLeaders('hitting', 'woba', LEADERS_LIMIT);
  const rows = data?.data.leaders ?? [];

  return (
    <Tile kicker="wOBA Leaders" rangeNote={`Top ${LEADERS_LIMIT} · 2026`} linkTo="/stats">
      {isLoading && <TileSkeleton rowCount={LEADERS_LIMIT} />}
      {isError && (
        <TileEmpty message="Leaderboard unavailable." onRetry={() => void refetch()} />
      )}
      {!isLoading && !isError && (
        <HitContent
          rows={rows.map((r) => ({
            playerId: r.person_id,
            fullName: r.full_name,
            valueLabel: typeof r.woba === 'number' ? r.woba.toFixed(3).replace(/^0\./, '.') : '—',
            context: `Rank #${r.rank}`,
          }))}
        />
      )}
    </Tile>
  );
}

interface TileProps {
  kicker: string;
  rangeNote: string;
  linkTo: string;
  children: React.ReactNode;
}

function Tile({ kicker, rangeNote, linkTo, children }: TileProps) {
  return (
    <div className="flex flex-col gap-3 rounded-m border border-hairline bg-surface-sunken/50 px-4 py-4">
      <div className="flex items-baseline justify-between">
        <span className="kicker text-accent-leather">{kicker}</span>
        <Link
          to={linkTo}
          className="text-[10.5px] font-semibold text-accent-leather hover:text-accent-leather-glow"
        >
          More →
        </Link>
      </div>
      <div className="mono text-[10px] uppercase tracking-[0.06em] text-paper-ink-soft">
        {rangeNote}
      </div>
      {children}
    </div>
  );
}

interface HitRow {
  playerId: number;
  fullName: string;
  valueLabel: string;
  context: string;
}

function HitContent({ rows }: { rows: readonly HitRow[] }) {
  if (rows.length === 0) return <TileEmpty message="No data yet." />;
  return (
    <div className="flex flex-col gap-2.5">
      {rows.map((r) => (
        <div key={r.playerId} className="flex items-center gap-3">
          <PlayerHeadshot playerId={r.playerId} playerName={r.fullName} size="sm" />
          <div className="min-w-0 flex-1">
            <div className="truncate text-[13px] font-semibold text-paper-ink">{r.fullName}</div>
            <div className="mono text-[10.5px] text-paper-ink-soft">{r.context}</div>
          </div>
          <div className="mono text-[15px] font-bold text-accent-leather">{r.valueLabel}</div>
        </div>
      ))}
    </div>
  );
}

function TileSkeleton({ rowCount = 1 }: { rowCount?: number }) {
  return (
    <div className="flex flex-col gap-2.5">
      {Array.from({ length: rowCount }).map((_, i) => (
        <div key={i} className="flex items-center gap-3">
          <Skeleton className="h-6 w-6 rounded" />
          <div className="flex flex-1 flex-col gap-1.5">
            <Skeleton className="h-3 w-3/4" />
            <Skeleton className="h-2 w-1/3" />
          </div>
          <Skeleton className="h-3.5 w-12" />
        </div>
      ))}
    </div>
  );
}

function TileEmpty({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="rounded-s border border-dashed border-hairline px-3 py-4 text-center text-[11.5px] text-paper-ink-soft">
      {message}
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="ml-2 text-accent-leather underline hover:text-accent-leather-glow"
        >
          Retry
        </button>
      )}
    </div>
  );
}
