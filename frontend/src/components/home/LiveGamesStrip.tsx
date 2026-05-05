import { LiveBadge } from '@/components/primitives/LiveBadge';
import { LiveGameCard } from '@/components/home/LiveGameCard';
import type { AppGame } from '@/types/app';

interface LiveGamesStripProps {
  liveGames: readonly AppGame[];
  isFetching: boolean;
  lastUpdatedAt: number | null;
}

export function LiveGamesStrip({ liveGames, isFetching, lastUpdatedAt }: LiveGamesStripProps) {
  if (liveGames.length === 0) return null;

  return (
    <section
      aria-label="Live games"
      className="rounded-l border border-hairline-strong bg-surface-elevated px-5 py-5 shadow-sm"
    >
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h2 className="text-[18px] font-bold tracking-[-0.005em] text-paper-ink">
            Live now
          </h2>
          <LiveBadge count={liveGames.length} />
        </div>
        <span className="text-[11px] text-paper-ink-soft">
          {isFetching ? 'Refreshing…' : 'Updated '}
          {!isFetching && (
            <span className="mono text-paper-ink-muted">{formatRelative(lastUpdatedAt)}</span>
          )}
        </span>
      </div>
      <div className="grid grid-cols-[repeat(auto-fill,minmax(280px,1fr))] gap-3">
        {liveGames.map((g) => (
          <LiveGameCard key={g.id} game={g} />
        ))}
      </div>
    </section>
  );
}

function formatRelative(ts: number | null): string {
  if (!ts) return '';
  const ageSec = Math.max(0, Math.floor((Date.now() - ts) / 1000));
  if (ageSec < 5) return 'just now';
  if (ageSec < 60) return `${ageSec}s ago`;
  const mins = Math.floor(ageSec / 60);
  return `${mins}m ago`;
}
