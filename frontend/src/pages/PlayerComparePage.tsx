import { useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';

import { AccoladesRow } from '@/components/AccoladesRow';
import { PlayerSearchPicker } from '@/components/PlayerSearchPicker';
import { Card } from '@/components/primitives/Card';
import { ErrorBanner } from '@/components/primitives/ErrorBanner';
import { Skeleton } from '@/components/primitives/Skeleton';
import { PlayerHeadshot } from '@/components/PlayerHeadshot';
import { HexagonalRadar } from '@/components/comparison/HexagonalRadar';
import { StatDetailTable } from '@/components/comparison/StatDetailTable';
import { PLAYER_RADAR_STATS } from '@/components/comparison/stat-extract';
import { useCompare } from '@/hooks/useCompare';
import { FEATURED_COMPARISONS, type FeaturedComparison } from '@/lib/featuredComparisons';
import { getMlbTeam } from '@/lib/mlbTeams';
import type { ComparePlayer } from '@/types/compare';

const MIN_IDS = 2;
const MAX_IDS = 4;

function parseIdsParam(raw: string | null): readonly number[] {
  if (!raw) return [];
  return raw
    .split(',')
    .map((s) => Number.parseInt(s.trim(), 10))
    .filter((n) => Number.isFinite(n) && n > 0);
}

export function PlayerComparePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const idsFromUrl = useMemo(() => parseIdsParam(searchParams.get('ids')), [searchParams]);

  const fallbackIds = FEATURED_COMPARISONS[0]?.playerIds ?? ([] as readonly number[]);
  const ids =
    idsFromUrl.length >= MIN_IDS && idsFromUrl.length <= MAX_IDS ? idsFromUrl : fallbackIds;

  const activeMatchup = FEATURED_COMPARISONS.find(
    (m) => ids.length === 2 && m.playerIds[0] === ids[0] && m.playerIds[1] === ids[1],
  );

  const compare = useCompare(ids);

  const selectedDisplay = useMemo(() => {
    const map = new Map<
      number,
      { person_id: number; full_name?: string | null; primary_position_abbr?: string | null }
    >();
    for (const p of compare.data?.data.players ?? []) {
      map.set(p.metadata.person_id, {
        person_id: p.metadata.person_id,
        full_name: p.metadata.full_name,
        primary_position_abbr: p.metadata.primary_position_abbr,
      });
    }
    return map;
  }, [compare.data]);

  function setIds(next: readonly number[]) {
    setSearchParams({ ids: next.join(',') });
  }
  function selectMatchup(m: FeaturedComparison) {
    setIds(m.playerIds);
  }
  function addId(personId: number) {
    if (ids.includes(personId)) return;
    if (ids.length >= MAX_IDS) return;
    setIds([...ids, personId]);
  }
  function removeId(personId: number) {
    if (ids.length <= MIN_IDS) return;
    setIds(ids.filter((id) => id !== personId));
  }

  return (
    <section className="page-data">
      <div className="kicker mb-2 text-accent-leather">Compare</div>
      <h1 className="display text-h1 text-paper-ink">Player Compare</h1>
      <p className="mt-1 max-w-2xl text-[13px] text-paper-ink-muted">
        Compare {MIN_IDS}–{MAX_IDS} MLB players. The radar overlays the first two players' six
        hero stats; full numerical detail lives in the table below.
      </p>

      <div className="mt-6">
        <PlayerSearchPicker
          selectedIds={ids}
          selectedDisplay={selectedDisplay}
          minIds={MIN_IDS}
          maxIds={MAX_IDS}
          onAdd={addId}
          onRemove={removeId}
          onPreset={selectMatchup}
          activePresetId={activeMatchup?.id ?? ''}
        />
      </div>

      <div className="mt-5">
        {compare.isLoading ? (
          <CompareSkeleton playerCount={ids.length} />
        ) : compare.isError ? (
          <ErrorBanner
            title="Couldn't load comparison"
            message={compare.error?.message ?? 'Please try again in a moment.'}
            onRetry={() => void compare.refetch()}
          />
        ) : (
          <ComparePanel players={compare.data?.data.players ?? []} onRemove={ids.length > MIN_IDS ? removeId : undefined} />
        )}
      </div>
    </section>
  );
}

interface ComparePanelProps {
  players: readonly ComparePlayer[];
  onRemove?: (personId: number) => void;
}

function ComparePanel({ players, onRemove }: ComparePanelProps) {
  if (players.length < MIN_IDS) {
    return (
      <Card>
        <div className="px-2 py-10 text-center text-[13px] text-paper-ink-soft">
          Comparison data unavailable.
        </div>
      </Card>
    );
  }

  // Radar overlay reads cleanly with two shapes; with 3-4 it gets noisy.
  // Restrict the radar to the first two players; the numerical-detail
  // table renders all of them.
  const radarA = players[0];
  const radarB = players[1];

  return (
    <div className="flex flex-col gap-5">
      <Card className="overflow-hidden">
        <div
          className="grid gap-6"
          style={{ gridTemplateColumns: `repeat(${players.length}, minmax(0, 1fr))` }}
        >
          {players.map((p, i) => (
            <PlayerHeader key={p.person_id} player={p} accent={i === 0} onRemove={onRemove} />
          ))}
        </div>
      </Card>

      <HexagonalRadar
        stats={PLAYER_RADAR_STATS}
        a={radarA}
        b={radarB}
        aName={radarA.metadata.full_name ?? 'Player A'}
        bName={radarB.metadata.full_name ?? 'Player B'}
      />

      {players.length > 2 && (
        <div className="rounded-m border border-hairline bg-surface-sunken/60 px-4 py-2 text-center text-[11.5px] italic text-paper-ink-soft">
          Radar overlays the first two players. All {players.length} players' values appear in the
          table below.
        </div>
      )}

      <StatDetailTable players={players} />
    </div>
  );
}

interface PlayerHeaderProps {
  player: ComparePlayer;
  accent?: boolean;
  onRemove?: (personId: number) => void;
}

function PlayerHeader({ player, accent = false, onRemove }: PlayerHeaderProps) {
  const teamId =
    (player.hitting?.team_id as number | undefined) ??
    (player.pitching?.team_id as number | undefined);
  const team = teamId != null ? getMlbTeam(teamId) : undefined;
  const subtitle = [team?.locationName, player.metadata.primary_position_abbr]
    .filter(Boolean)
    .join(' · ');

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-start gap-3">
        <PlayerHeadshot
          playerId={player.metadata.person_id}
          playerName={player.metadata.full_name}
          size="lg"
        />
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <div
            className={[
              'kicker',
              accent ? 'text-accent-leather' : 'text-paper-ink-soft',
            ].join(' ')}
          >
            {subtitle || '—'}
          </div>
          <div className="truncate text-xl font-bold -tracking-[0.01em] text-paper-ink">
            {player.metadata.full_name}
          </div>
          {player.metadata.bat_side && player.metadata.pitch_hand && (
            <div className="mono text-[11px] text-paper-ink-soft">
              B/T: {player.metadata.bat_side} / {player.metadata.pitch_hand}
              {player.metadata.height ? ` · ${player.metadata.height}` : ''}
            </div>
          )}
        </div>
        {onRemove && (
          <button
            type="button"
            onClick={() => onRemove(player.metadata.person_id)}
            aria-label={`Remove ${player.metadata.full_name}`}
            className="rounded-s border border-hairline px-1.5 py-0.5 text-[11px] text-paper-ink-soft hover:border-bad/50 hover:text-bad"
          >
            ×
          </button>
        )}
      </div>
      <AccoladesRow awards={player.awards ?? null} />
    </div>
  );
}

function CompareSkeleton({ playerCount }: { playerCount: number }) {
  const cols = Math.max(MIN_IDS, Math.min(MAX_IDS, playerCount));
  return (
    <div className="flex flex-col gap-5">
      <Card>
        <div
          className="grid gap-6"
          style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}
        >
          {Array.from({ length: cols }).map((_, i) => (
            <div key={i} className="flex items-start gap-3">
              <Skeleton className="h-24 w-24 rounded-full" />
              <div className="flex flex-col gap-2">
                <Skeleton className="h-3 w-20" />
                <Skeleton className="h-5 w-32" />
                <Skeleton className="h-3 w-24" />
              </div>
            </div>
          ))}
        </div>
      </Card>
      <Skeleton className="h-[500px] w-full rounded-l" />
      <Skeleton className="h-[300px] w-full rounded-l" />
    </div>
  );
}
