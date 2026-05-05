import { useState } from 'react';

import { Card } from '@/components/primitives/Card';
import { PlayerHeadshot } from '@/components/PlayerHeadshot';
import { Skeleton } from '@/components/primitives/Skeleton';
import { useCompare } from '@/hooks/useCompare';
import { FEATURED_COMPARISONS, type FeaturedComparison } from '@/lib/featuredComparisons';
import { getMlbTeam } from '@/lib/mlbTeams';
import {
  compareStatBetter,
  formatStat,
  isAscendingStat,
  parseStatNumber,
} from '@/lib/stats';
import type { ComparePlayer } from '@/types/compare';

type StatGroup = 'hitting' | 'pitching';

const HITTING_ROWS: readonly { token: string; label: string }[] = [
  { token: 'avg', label: 'AVG' },
  { token: 'home_runs', label: 'HR' },
  { token: 'rbi', label: 'RBI' },
  { token: 'ops', label: 'OPS' },
  { token: 'woba', label: 'wOBA' },
  { token: 'ops_plus', label: 'OPS+' },
];

const PITCHING_ROWS: readonly { token: string; label: string }[] = [
  { token: 'era', label: 'ERA' },
  { token: 'strikeouts', label: 'K' },
  { token: 'whip', label: 'WHIP' },
  { token: 'fip', label: 'FIP' },
  { token: 'wins', label: 'W' },
  { token: 'saves', label: 'SV' },
];

export function CompareStrip() {
  const [activeId, setActiveId] = useState<string>(FEATURED_COMPARISONS[0]?.id ?? '');
  const matchup = FEATURED_COMPARISONS.find((m) => m.id === activeId);
  const ids = matchup ? matchup.playerIds : ([] as readonly number[]);
  const compare = useCompare(ids);

  return (
    <div className="flex flex-col gap-3">
      <MatchupTabs activeId={activeId} onSelect={setActiveId} />
      <CompareBody matchup={matchup} compare={compare} />
    </div>
  );
}

interface MatchupTabsProps {
  activeId: string;
  onSelect: (id: string) => void;
}

function MatchupTabs({ activeId, onSelect }: MatchupTabsProps) {
  return (
    <div
      className="-mx-1 flex gap-1.5 overflow-x-auto px-1 pb-1"
      role="tablist"
      aria-label="Featured player comparisons"
    >
      {FEATURED_COMPARISONS.map((m) => {
        const active = m.id === activeId;
        return (
          <button
            key={m.id}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onSelect(m.id)}
            className={[
              'whitespace-nowrap rounded-s px-3 py-1.5 text-[12px] font-semibold transition-colors',
              active
                ? 'bg-accent text-white'
                : 'bg-surface-2 text-paper-3 hover:bg-surface-3',
            ].join(' ')}
          >
            {m.title}
          </button>
        );
      })}
    </div>
  );
}

interface CompareBodyProps {
  matchup: FeaturedComparison | undefined;
  compare: ReturnType<typeof useCompare>;
}

function CompareBody({ matchup, compare }: CompareBodyProps) {
  if (!matchup) {
    return (
      <Card>
        <div className="px-2 py-6 text-center text-[12px] text-paper-4">
          Select a matchup to compare
        </div>
      </Card>
    );
  }

  if (compare.isLoading) {
    return <CompareSkeleton subtitle={matchup.subtitle} />;
  }
  if (compare.isError) {
    return (
      <Card>
        <div className="px-2 py-6 text-center text-[12px] text-paper-4">
          Couldn't load comparison.{' '}
          <button
            type="button"
            onClick={() => void compare.refetch()}
            className="text-accent underline hover:text-accent-glow"
          >
            Retry
          </button>
        </div>
      </Card>
    );
  }

  const players = compare.data?.data.players ?? [];
  if (players.length < 2) {
    return (
      <Card>
        <div className="px-2 py-6 text-center text-[12px] text-paper-4">
          Comparison data unavailable.
        </div>
      </Card>
    );
  }

  const [a, b] = players;
  return <Comparison subtitle={matchup.subtitle} a={a} b={b} />;
}

interface ComparisonProps {
  subtitle: string;
  a: ComparePlayer;
  b: ComparePlayer;
}

function Comparison({ subtitle, a, b }: ComparisonProps) {
  // Resolve which group both players share. Hitter-vs-pitcher → no shared
  // group → render the "incomparable" fallback. Both-groups-null → render
  // the "insufficient data" fallback (e.g. Germán Márquez, trade
  // call-ups, mid-season IL returns).
  const aHas = { hitting: a.hitting != null, pitching: a.pitching != null };
  const bHas = { hitting: b.hitting != null, pitching: b.pitching != null };

  let group: StatGroup | null = null;
  if (aHas.hitting && bHas.hitting) group = 'hitting';
  else if (aHas.pitching && bHas.pitching) group = 'pitching';

  if (group === null) {
    const noData = !(aHas.hitting || aHas.pitching) || !(bHas.hitting || bHas.pitching);
    return (
      <Card>
        <CompareHeader subtitle={subtitle} a={a} b={b} />
        <div className="px-2 py-6 text-center text-[12px] text-paper-4">
          {noData
            ? 'Insufficient season data for at least one player.'
            : 'Player types incomparable (one hitter, one pitcher).'}
        </div>
      </Card>
    );
  }

  const rows = group === 'hitting' ? HITTING_ROWS : PITCHING_ROWS;
  const aStats = (group === 'hitting' ? a.hitting : a.pitching) as Record<string, unknown>;
  const bStats = (group === 'hitting' ? b.hitting : b.pitching) as Record<string, unknown>;

  return (
    <Card>
      <CompareHeader subtitle={subtitle} a={a} b={b} />
      <div className="mt-4 flex flex-col gap-3">
        {rows.map((row) => (
          <StatRow
            key={row.token}
            stat={row.token}
            label={row.label}
            valueA={aStats[row.token] as number | string | undefined}
            valueB={bStats[row.token] as number | string | undefined}
          />
        ))}
      </div>
    </Card>
  );
}

interface CompareHeaderProps {
  subtitle: string;
  a: ComparePlayer;
  b: ComparePlayer;
}

function CompareHeader({ subtitle, a, b }: CompareHeaderProps) {
  return (
    <>
      <div className="mb-2 text-[10px] font-semibold uppercase tracking-[0.06em] text-paper-4">
        {subtitle}
      </div>
      <div className="grid grid-cols-2 gap-7 border-b border-hairline-strong pb-4">
        <CompareSide player={a} accent />
        <CompareSide player={b} />
      </div>
    </>
  );
}

interface CompareSideProps {
  player: ComparePlayer;
  accent?: boolean;
}

function CompareSide({ player, accent = false }: CompareSideProps) {
  // The stats blocks may carry a team_id; fall back to undefined → unknown chip.
  const teamId =
    (player.hitting?.team_id as number | undefined) ??
    (player.pitching?.team_id as number | undefined);
  const team = teamId != null ? getMlbTeam(teamId) : undefined;
  const subtitle = [team?.locationName, player.metadata.primary_position_abbr]
    .filter(Boolean)
    .join(' · ');

  return (
    <div className="flex items-center gap-3.5">
      <PlayerHeadshot
        playerId={player.metadata.person_id}
        playerName={player.metadata.full_name}
        size="md"
      />
      <div className="flex flex-col gap-0.5">
        <div className={['kicker', accent ? 'text-accent' : 'text-paper-4'].join(' ')}>
          {subtitle || '—'}
        </div>
        <div className="text-lg font-bold -tracking-[0.01em] text-paper">
          {player.metadata.full_name}
        </div>
      </div>
    </div>
  );
}

interface StatRowProps {
  stat: string;
  label: string;
  valueA: number | string | null | undefined;
  valueB: number | string | null | undefined;
}

function StatRow({ stat, label, valueA, valueB }: StatRowProps) {
  const winner = compareStatBetter(stat, valueA, valueB);
  const ascending = isAscendingStat(stat);
  const na = parseStatNumber(valueA);
  const nb = parseStatNumber(valueB);

  // Self-scaling per-row max with 5% headroom. For ascending stats the bar
  // is inverted: we render (max - value) instead of value, so visually-
  // longer = better remains the user's mental model.
  const both = na !== null && nb !== null;
  const max = both ? Math.max(na!, nb!) * 1.05 || 1 : 1;
  const fillA = both
    ? ascending
      ? Math.max(0, max - na!) / max
      : na! / max
    : 0;
  const fillB = both
    ? ascending
      ? Math.max(0, max - nb!) / max
      : nb! / max
    : 0;

  const aWins = winner === 'a';
  const bWins = winner === 'b';

  return (
    <div className="grid grid-cols-[1fr_60px_1fr] items-center gap-4">
      <div className="flex items-center justify-end gap-2.5">
        <span
          className={[
            'mono text-[13px]',
            aWins ? 'font-bold text-accent' : 'font-medium text-paper-3',
          ].join(' ')}
        >
          {formatStat(stat, valueA ?? null)}
        </span>
        <div className="relative h-1.5 w-[180px] overflow-hidden rounded-s bg-surface-3">
          <div
            className={[
              'absolute inset-y-0 right-0 transition-[width] duration-300',
              aWins ? 'bg-accent' : 'bg-paper-5',
            ].join(' ')}
            style={{ width: `${fillA * 100}%` }}
          />
        </div>
      </div>
      <span className="kicker text-center text-[10px]">{label}</span>
      <div className="flex items-center gap-2.5">
        <div className="relative h-1.5 w-[180px] overflow-hidden rounded-s bg-surface-3">
          <div
            className={[
              'h-full transition-[width] duration-300',
              bWins ? 'bg-accent' : 'bg-paper-5',
            ].join(' ')}
            style={{ width: `${fillB * 100}%` }}
          />
        </div>
        <span
          className={[
            'mono text-[13px]',
            bWins ? 'font-bold text-accent' : 'font-medium text-paper-3',
          ].join(' ')}
        >
          {formatStat(stat, valueB ?? null)}
        </span>
      </div>
    </div>
  );
}

function CompareSkeleton({ subtitle }: { subtitle: string }) {
  return (
    <Card>
      <div className="mb-2 text-[10px] font-semibold uppercase tracking-[0.06em] text-paper-4">
        {subtitle}
      </div>
      <div className="mb-4 grid grid-cols-2 gap-7 border-b border-hairline-strong pb-4">
        {[0, 1].map((i) => (
          <div key={i} className="flex items-center gap-3.5">
            <Skeleton className="h-[46px] w-[46px] rounded" />
            <div className="flex flex-col gap-1.5">
              <Skeleton className="h-3 w-20" />
              <Skeleton className="h-4 w-32" />
            </div>
          </div>
        ))}
      </div>
      <div className="flex flex-col gap-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="grid grid-cols-[1fr_60px_1fr] items-center gap-4">
            <div className="flex items-center justify-end gap-2.5">
              <Skeleton className="h-3 w-10" />
              <Skeleton className="h-1.5 w-[180px]" />
            </div>
            <Skeleton className="mx-auto h-2.5 w-8" />
            <div className="flex items-center gap-2.5">
              <Skeleton className="h-1.5 w-[180px]" />
              <Skeleton className="h-3 w-10" />
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}
