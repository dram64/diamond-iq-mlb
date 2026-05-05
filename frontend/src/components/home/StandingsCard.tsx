/**
 * StandingsCard — single-division standings card for the Leaders section.
 *
 * Filters the full-league standings response to one division and renders a
 * compact 5-row table inside the existing LeaderCard primitive. v1 ships
 * single-division; multi-division extension via `divisionIds={[...]}` is
 * a future polish.
 */

import { Link } from 'react-router-dom';

import { Card } from '@/components/primitives/Card';
import { Skeleton } from '@/components/primitives/Skeleton';
import { TeamChip } from '@/components/primitives/TeamChip';
import { useStandings } from '@/hooks/useStandings';
import { getMlbDivision } from '@/lib/mlbDivisions';
import { getMlbTeam } from '@/lib/mlbTeams';
import type { StandingsRecord } from '@/types/standings';

interface StandingsCardProps {
  /** Single division id (200..205). For multi-division support, extend later. */
  divisionId: number;
  /** Override the default "Standings · {abbr}" title. */
  title?: string;
}

export function StandingsCard({ divisionId, title }: StandingsCardProps) {
  const { data, isLoading, isError, refetch } = useStandings();
  const division = getMlbDivision(divisionId);
  const resolvedTitle = title ?? `Standings · ${division?.abbr ?? ''}`;

  return (
    <Card flush className="overflow-hidden">
      <div className="flex items-center justify-between border-b border-hairline-strong px-4 py-3">
        <h4>{resolvedTitle}</h4>
        <Link to="/teams" className="text-[11px] font-semibold text-accent hover:text-accent-glow">
          View all →
        </Link>
      </div>
      <ColumnHeaders />
      <div>
        {isLoading ? (
          <SkeletonRows />
        ) : isError ? (
          <ErrorState onRetry={() => void refetch()} />
        ) : (
          <DivisionRows divisionId={divisionId} teams={data?.data.teams ?? []} />
        )}
      </div>
    </Card>
  );
}

function ColumnHeaders() {
  const cols = ['', 'W-L', 'GB', 'Run diff'];
  return (
    <div className="grid grid-cols-[22px_1fr_52px_42px_58px] items-center gap-2 border-b border-hairline bg-surface-2 px-4 py-2">
      {cols.map((c, i) => (
        <span
          key={i}
          className={[
            'text-[9.5px] font-bold uppercase tracking-[0.06em] text-paper-4',
            i < 2 ? 'text-left' : 'text-right',
          ].join(' ')}
        >
          {c}
        </span>
      ))}
    </div>
  );
}

interface DivisionRowsProps {
  divisionId: number;
  teams: readonly StandingsRecord[];
}

function DivisionRows({ divisionId, teams }: DivisionRowsProps) {
  const filtered = teams
    .filter((t) => t.division_id === divisionId)
    .sort((a, b) => a.division_rank - b.division_rank);

  if (filtered.length === 0) {
    return (
      <div className="px-4 py-6 text-center text-[12px] text-paper-4">No standings available</div>
    );
  }

  return (
    <>
      {filtered.map((team) => (
        <StandingsRow key={team.team_id} team={team} />
      ))}
    </>
  );
}

function StandingsRow({ team }: { team: StandingsRecord }) {
  const meta = getMlbTeam(team.team_id);
  const abbr = meta?.abbreviation ?? '?';
  const color = meta?.primaryColor ?? '';
  const logoPath = meta?.logoPath;
  const cityOrName = meta?.locationName ?? team.team_name;
  const runDiff = team.run_differential;
  const runDiffSign = runDiff > 0 ? '+' : '';
  const runDiffClass = runDiff > 0 ? 'text-good' : runDiff < 0 ? 'text-bad' : 'text-paper-2';

  return (
    <div className="grid grid-cols-[22px_1fr_52px_42px_58px] items-center gap-2 border-b border-hairline px-4 py-2.5 last:border-b-0">
      <span className="mono text-[11px] text-paper-4">{team.division_rank}</span>
      <div className="flex min-w-0 items-center gap-2">
        <TeamChip abbr={abbr} color={color} logoPath={logoPath} size={16} />
        <span className="truncate text-[12.5px] text-paper">{cityOrName}</span>
      </div>
      <span className="mono text-right text-[12px] text-paper-2">
        {team.wins}-{team.losses}
      </span>
      <span className="mono text-right text-[12px] text-paper-4">{team.games_back}</span>
      <span className={['mono text-right text-[12px] font-medium', runDiffClass].join(' ')}>
        {runDiffSign}
        {runDiff}
      </span>
    </div>
  );
}

function SkeletonRows() {
  return (
    <>
      {Array.from({ length: 5 }).map((_, i) => (
        <div
          key={i}
          className="grid grid-cols-[22px_1fr_52px_42px_58px] items-center gap-2 border-b border-hairline px-4 py-2.5 last:border-b-0"
          aria-hidden="true"
        >
          <Skeleton className="h-3 w-3" />
          <div className="flex items-center gap-2">
            <Skeleton className="h-4 w-4 rounded" />
            <Skeleton className="h-3 w-20" />
          </div>
          <Skeleton className="ml-auto h-3 w-10" />
          <Skeleton className="ml-auto h-3 w-6" />
          <Skeleton className="ml-auto h-3 w-10" />
        </div>
      ))}
    </>
  );
}

function ErrorState({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="px-4 py-6 text-center text-[12px] text-paper-4">
      Couldn't load standings.{' '}
      <button
        type="button"
        onClick={onRetry}
        className="text-accent underline hover:text-accent-glow"
      >
        Retry
      </button>
    </div>
  );
}
