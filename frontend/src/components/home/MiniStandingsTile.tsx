import { Link } from 'react-router-dom';

import { Skeleton } from '@/components/primitives/Skeleton';
import { groupByDivision } from '@/lib/mlbDivisions';
import { getMlbTeam } from '@/lib/mlbTeams';
import { useStandings } from '@/hooks/useStandings';
import type { StandingsRecord } from '@/types/standings';

const TOP_N = 3;

export function MiniStandingsTile() {
  const { data, isLoading, isError } = useStandings();

  return (
    <section
      aria-label="Mini standings"
      className="flex flex-col gap-3 rounded-l border border-hairline-strong bg-surface-elevated p-5 shadow-sm"
    >
      <div className="flex items-baseline justify-between border-b border-hairline pb-2">
        <h3 className="text-[15px] font-bold tracking-[-0.005em] text-paper-ink">
          Mini Standings
        </h3>
        <Link
          to="/teams"
          className="text-[10.5px] font-semibold text-accent-leather hover:text-accent-leather-glow"
        >
          All teams →
        </Link>
      </div>

      {isLoading && <MiniStandingsSkeleton />}
      {isError && <Empty message="Standings unavailable." />}
      {!isLoading && !isError && data && (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {groupByDivision(data.data.teams)
            .map((g) => ({
              division: g.division,
              top: [...g.teams]
                .sort((a, b) => a.division_rank - b.division_rank)
                .slice(0, TOP_N),
            }))
            .map(({ division, top }) => (
              <DivisionBlock key={division.id} divisionAbbr={division.abbr} top={top} />
            ))}
        </div>
      )}
    </section>
  );
}

function DivisionBlock({
  divisionAbbr,
  top,
}: {
  divisionAbbr: string;
  top: readonly StandingsRecord[];
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="kicker text-accent-leather">{divisionAbbr}</span>
      {top.map((t) => (
        <Link
          key={t.team_id}
          to={`/teams/${t.team_id}`}
          className="grid grid-cols-[20px_1fr_auto_auto] items-center gap-2 rounded-s px-1 py-0.5 transition-colors duration-200 hover:bg-surface-sunken/60"
        >
          <TeamLogo teamId={t.team_id} />
          <span className="truncate text-[12px] font-semibold text-paper-ink">
            {getMlbTeam(t.team_id)?.abbreviation ?? t.team_name}
          </span>
          <span className="mono text-[11px] text-paper-ink-muted">
            {t.wins}–{t.losses}
          </span>
          <span className="mono w-7 text-right text-[10.5px] text-paper-ink-soft">
            {t.games_back || '—'}
          </span>
        </Link>
      ))}
    </div>
  );
}

function TeamLogo({ teamId }: { teamId: number }) {
  const meta = getMlbTeam(teamId);
  if (!meta) return <span className="block h-5 w-5 rounded-full bg-surface-sunken" aria-hidden="true" />;
  return (
    <img
      src={meta.logoPath}
      alt=""
      width={20}
      height={20}
      loading="lazy"
      className="h-5 w-5 shrink-0 object-contain"
    />
  );
}

function MiniStandingsSkeleton() {
  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="flex flex-col gap-1.5">
          <Skeleton className="h-2.5 w-16" />
          {Array.from({ length: TOP_N }).map((_, j) => (
            <div key={j} className="grid grid-cols-[20px_1fr_auto_auto] items-center gap-2">
              <Skeleton className="h-5 w-5 rounded-full" />
              <Skeleton className="h-3 w-12" />
              <Skeleton className="h-3 w-10" />
              <Skeleton className="h-3 w-7" />
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

function Empty({ message }: { message: string }) {
  return (
    <div className="rounded-s border border-dashed border-hairline px-3 py-4 text-center text-[11.5px] text-paper-ink-soft">
      {message}
    </div>
  );
}
