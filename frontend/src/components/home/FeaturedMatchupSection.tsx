import { Link } from 'react-router-dom';

import { Card } from '@/components/primitives/Card';
import { ErrorBanner } from '@/components/primitives/ErrorBanner';
import { Skeleton } from '@/components/primitives/Skeleton';
import { useFeaturedMatchup } from '@/hooks/useFeaturedMatchup';
import { getMlbTeam } from '@/lib/mlbTeams';
import type { FeaturedMatchupTeam } from '@/types/featuredMatchup';

export function FeaturedMatchupSection() {
  const { data, isLoading, isError, error, refetch } = useFeaturedMatchup();

  if (isLoading) return <SkeletonCard />;
  if (isError) {
    return (
      <ErrorBanner
        title="Couldn't load today's featured matchup"
        message={error?.message ?? 'Please try again shortly.'}
        onRetry={() => void refetch()}
      />
    );
  }

  const matchup = data?.data;
  if (!matchup || matchup.teams.length < 2) {
    return (
      <Card>
        <div className="px-2 py-6 text-center text-[12px] text-paper-4">
          Today's featured matchup is unavailable.
        </div>
      </Card>
    );
  }

  const [a, b] = matchup.teams;
  const target = `/compare-teams?ids=${matchup.team_ids.join(',')}`;
  return (
    <Card className="overflow-hidden">
      <Link
        to={target}
        className="group flex flex-col gap-5 transition hover:opacity-95"
        aria-label={`Compare ${a.team_name ?? a.abbreviation ?? 'team A'} vs ${b.team_name ?? b.abbreviation ?? 'team B'}`}
      >
        <div className="flex items-center justify-between border-b border-hairline-strong pb-3">
          <div className="kicker text-accent">Today's Featured Matchup</div>
          <div className="mono text-[10.5px] text-paper-4">
            {matchup.date} · {matchup.selection_reason}
          </div>
        </div>

        <div className="grid grid-cols-1 gap-6 sm:grid-cols-[1fr_auto_1fr] sm:items-center">
          <TeamSide team={a} alignRight={false} />
          <div className="hidden text-center sm:block">
            <span className="mono text-[26px] font-bold text-paper-4">vs</span>
          </div>
          <TeamSide team={b} alignRight />
        </div>

        <div className="flex items-center justify-between border-t border-hairline pt-3 text-[12px] text-paper-3">
          <span>Side-by-side team stats, run differential, and analysis →</span>
          <span className="text-accent group-hover:underline">Open compare →</span>
        </div>
      </Link>
    </Card>
  );
}

interface TeamSideProps {
  team: FeaturedMatchupTeam;
  alignRight: boolean;
}

function TeamSide({ team, alignRight }: TeamSideProps) {
  const meta = getMlbTeam(team.team_id);
  return (
    <div
      className={[
        'flex items-center gap-4',
        alignRight ? 'sm:flex-row-reverse sm:text-right' : '',
      ].join(' ')}
    >
      {meta ? (
        <img
          src={meta.logoPath}
          alt={meta.fullName}
          width={72}
          height={72}
          loading="lazy"
          className="h-18 w-18 shrink-0 object-contain"
        />
      ) : (
        <div className="h-18 w-18 shrink-0 rounded-full bg-surface-3" />
      )}
      <div className="flex flex-col gap-0.5">
        <div className="kicker text-paper-4">
          <span
            className={[
              'inline-block rounded-full px-2 py-0.5 text-[9.5px] font-bold',
              team.league === 'AL' ? 'bg-accent/15 text-accent' : 'bg-paper-5/20 text-paper-3',
            ].join(' ')}
          >
            {team.league} #1
          </span>
        </div>
        <div className="text-2xl font-bold -tracking-[0.01em] text-paper">
          {meta?.fullName ?? team.team_name ?? team.abbreviation ?? '—'}
        </div>
        <div className="mono text-[12px] text-paper-3">
          <span className="font-semibold">
            {team.wins}-{team.losses}
          </span>
          {team.run_differential !== null && (
            <span className="ml-2 text-paper-4">
              {team.run_differential >= 0 ? '+' : ''}
              {team.run_differential} run diff
            </span>
          )}
        </div>
        <div className="mono text-[11px] text-paper-4">
          {team.highlight_stats.ops && <span>OPS {team.highlight_stats.ops}</span>}
          {team.highlight_stats.ops && team.highlight_stats.era && <span> · </span>}
          {team.highlight_stats.era && <span>ERA {team.highlight_stats.era}</span>}
        </div>
      </div>
    </div>
  );
}

function SkeletonCard() {
  return (
    <Card>
      <Skeleton className="mb-4 h-3 w-48" />
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-[1fr_auto_1fr] sm:items-center">
        {[0, 1].map((i) => (
          <div key={i} className="flex items-center gap-4">
            <Skeleton className="h-18 w-18" />
            <div className="flex flex-col gap-2">
              <Skeleton className="h-3 w-16" />
              <Skeleton className="h-6 w-44" />
              <Skeleton className="h-3 w-32" />
              <Skeleton className="h-3 w-28" />
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}
