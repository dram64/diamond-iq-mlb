import { Link } from 'react-router-dom';

import { Skeleton } from '@/components/primitives/Skeleton';
import { useStandings } from '@/hooks/useStandings';
import { getMlbDivision } from '@/lib/mlbDivisions';
import { getMlbTeam } from '@/lib/mlbTeams';
import type { StandingsRecord } from '@/types/standings';

export function TeamSpotlightTile() {
  const { data, isLoading, isError } = useStandings();

  const top = pickTopRunDifferential(data?.data.teams ?? []);

  return (
    <section
      aria-label="Team of the day"
      className="flex flex-col gap-3 rounded-l border border-hairline-strong bg-surface-elevated p-5 shadow-sm"
    >
      <div className="flex items-baseline justify-between border-b border-hairline pb-2">
        <h3 className="text-[15px] font-bold tracking-[-0.005em] text-paper-ink">
          Team of the Day
        </h3>
        <span className="kicker text-paper-ink-soft">Best run diff</span>
      </div>

      {isLoading && <SpotlightSkeleton />}
      {isError && <Empty message="Standings unavailable." />}
      {!isLoading && !isError && !top && <Empty message="No data yet." />}
      {!isLoading && !isError && top && <SpotlightCard team={top} />}
    </section>
  );
}

function SpotlightCard({ team }: { team: StandingsRecord }) {
  const meta = getMlbTeam(team.team_id);
  const division = getMlbDivision(team.division_id);
  return (
    <Link
      to={`/teams/${team.team_id}`}
      className="group flex flex-col gap-3 rounded-m border border-hairline bg-surface-sunken/40 p-4 transition-colors duration-200 hover:bg-surface-sunken/70"
    >
      <div className="flex items-center gap-4">
        {meta ? (
          <img
            src={meta.logoPath}
            alt={meta.fullName}
            width={72}
            height={72}
            loading="lazy"
            className="h-[72px] w-[72px] shrink-0 object-contain"
          />
        ) : (
          <div className="h-[72px] w-[72px] shrink-0 rounded-full bg-surface-sunken" />
        )}
        <div className="flex min-w-0 flex-col gap-1">
          <span className="kicker text-accent-leather">Team of the Day</span>
          <h4 className="truncate text-[18px] font-bold leading-tight text-paper-ink">
            {meta?.fullName ?? team.team_name}
          </h4>
          <span className="mono text-[10.5px] text-paper-ink-soft">
            {division?.abbr ?? '—'}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3 border-t border-hairline pt-3">
        <Stat label="Record" value={`${team.wins}–${team.losses}`} />
        <Stat
          label="Run diff"
          value={`${team.run_differential >= 0 ? '+' : ''}${team.run_differential}`}
          accent
        />
        <Stat label="Div rank" value={`#${team.division_rank}`} />
      </div>

      <div className="flex items-center justify-end pt-1">
        <span className="text-[11.5px] font-semibold text-accent-leather group-hover:text-accent-leather-glow">
          View team →
        </span>
      </div>
    </Link>
  );
}

function Stat({ label, value, accent = false }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="kicker text-paper-ink-soft">{label}</span>
      <span
        className={[
          'mono text-[15px] font-bold',
          accent ? 'text-accent-leather' : 'text-paper-ink',
        ].join(' ')}
      >
        {value}
      </span>
    </div>
  );
}

function pickTopRunDifferential(teams: readonly StandingsRecord[]): StandingsRecord | null {
  if (teams.length === 0) return null;
  let best = teams[0];
  for (const t of teams) {
    if (t.run_differential > best.run_differential) best = t;
  }
  return best;
}

function SpotlightSkeleton() {
  return (
    <div className="flex flex-col gap-3 rounded-m border border-hairline bg-surface-sunken/40 p-4">
      <div className="flex items-center gap-4">
        <Skeleton className="h-[72px] w-[72px] rounded-full" />
        <div className="flex flex-col gap-1.5">
          <Skeleton className="h-3 w-24" />
          <Skeleton className="h-5 w-44" />
          <Skeleton className="h-3 w-20" />
        </div>
      </div>
      <div className="grid grid-cols-3 gap-3 border-t border-hairline pt-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="flex flex-col gap-1">
            <Skeleton className="h-2.5 w-12" />
            <Skeleton className="h-4 w-10" />
          </div>
        ))}
      </div>
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
