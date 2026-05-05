import { Link } from 'react-router-dom';

import { Card } from '@/components/primitives/Card';
import { Skeleton } from '@/components/primitives/Skeleton';
import { TeamChip } from '@/components/primitives/TeamChip';
import { useStandings } from '@/hooks/useStandings';
import { groupByDivision, type MlbDivision } from '@/lib/mlbDivisions';
import { getMlbTeam } from '@/lib/mlbTeams';
import type { StandingsRecord } from '@/types/standings';

export function TeamGridSection() {
  const { data, isLoading, isError, refetch } = useStandings();

  if (isLoading) {
    return <TeamGridSkeleton />;
  }
  if (isError) {
    return (
      <Card>
        <div className="px-2 py-6 text-center text-[12px] text-paper-4">
          Couldn't load standings.{' '}
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

  const teams = data?.data.teams ?? [];
  if (teams.length === 0) {
    return (
      <Card>
        <div className="px-2 py-6 text-center text-[12px] text-paper-4">
          Standings not yet available
        </div>
      </Card>
    );
  }

  // Sort each division's teams by division_rank (numeric after parse boundary).
  const sorted = [...teams].sort((a, b) => a.division_rank - b.division_rank);
  const groups = groupByDivision(sorted);
  const al = groups.filter((g) => g.division.league === 'AL');
  const nl = groups.filter((g) => g.division.league === 'NL');

  return (
    <div className="flex flex-col gap-6">
      <LeagueBlock label="American League" groups={al} />
      <LeagueBlock label="National League" groups={nl} />
    </div>
  );
}

interface LeagueBlockProps {
  label: string;
  groups: { division: MlbDivision; teams: StandingsRecord[] }[];
}

function LeagueBlock({ label, groups }: LeagueBlockProps) {
  return (
    <div>
      <div className="mb-2 text-[10px] font-semibold uppercase tracking-[0.08em] text-paper-4">
        {label}
      </div>
      <div className="flex flex-col gap-3">
        {groups.map((g) => (
          <DivisionRow key={g.division.id} division={g.division} teams={g.teams} />
        ))}
      </div>
    </div>
  );
}

interface DivisionRowProps {
  division: MlbDivision;
  teams: StandingsRecord[];
}

function DivisionRow({ division, teams }: DivisionRowProps) {
  return (
    <div>
      <div className="mb-1.5 text-[11px] font-bold tracking-tight text-paper-2">
        {division.abbr}
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {teams.map((team) => (
          <TeamCard key={team.team_id} team={team} />
        ))}
      </div>
    </div>
  );
}

interface TeamCardProps {
  team: StandingsRecord;
}

export function TeamCard({ team }: TeamCardProps) {
  const meta = getMlbTeam(team.team_id);
  const abbr = meta?.abbreviation ?? '?';
  const color = meta?.primaryColor ?? '';
  const logoPath = meta?.logoPath;
  const cityOrName = meta?.locationName ?? team.team_name;
  const teamName = meta?.teamName ?? '';

  const streakIsWin = !!team.streak_code && team.streak_code.startsWith('W');
  const runDiff = team.run_differential;
  const runDiffSign = runDiff > 0 ? '+' : '';
  const winPct = parsePct(team.pct);

  return (
    <Link
      to={`/teams/${team.team_id}`}
      className="group flex flex-col gap-2.5 rounded-m border border-hairline-strong bg-white p-3.5 shadow-sm transition hover:shadow-md"
    >
      <div className="flex items-center gap-2.5">
        <TeamChip abbr={abbr} color={color} logoPath={logoPath} size={32} />
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-bold -tracking-[0.01em] text-paper">
            {cityOrName}
          </div>
          <div className="mono text-[10.5px] text-paper-4">{teamName}</div>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-x-2 gap-y-1.5 border-t border-hairline pt-2">
        <MiniStat label="Record" value={`${team.wins}-${team.losses}`} />
        <MiniStat label="Last 10" value={team.last_ten_record ?? '—'} />
        <MiniStat
          label="Streak"
          value={team.streak_code ?? '—'}
          tone={team.streak_code ? (streakIsWin ? 'good' : 'bad') : 'default'}
        />
        <MiniStat
          label="Run diff"
          value={`${runDiffSign}${runDiff}`}
          tone={runDiff > 0 ? 'good' : runDiff < 0 ? 'bad' : 'default'}
        />
      </div>
      <div className="mt-0.5 h-[3px] overflow-hidden rounded-s bg-surface-3">
        <div
          className={['h-full', winPct > 0.55 ? 'bg-accent' : 'bg-paper-5'].join(' ')}
          style={{ width: `${Math.min(100, Math.max(0, winPct * 100))}%` }}
        />
      </div>
    </Link>
  );
}

function MiniStat({
  label,
  value,
  tone = 'default',
}: {
  label: string;
  value: string;
  tone?: 'default' | 'good' | 'bad' | 'accent';
}) {
  const color =
    tone === 'good'
      ? 'text-good'
      : tone === 'bad'
        ? 'text-bad'
        : tone === 'accent'
          ? 'text-accent'
          : 'text-paper-2';
  return (
    <div>
      <div className="kicker mb-0.5 text-[8.5px]">{label}</div>
      <div className={`mono text-[12.5px] font-semibold ${color}`}>{value}</div>
    </div>
  );
}

/** Parse ".643" / "1.000" winning-percentage strings into a 0..1 number. */
function parsePct(value: string | null | undefined): number {
  if (!value) return 0;
  const n = Number.parseFloat(value);
  return Number.isFinite(n) ? n : 0;
}

function TeamGridSkeleton() {
  // Render two league blocks with 3 division rows × 5 tiles each (30 total).
  return (
    <div className="flex flex-col gap-6">
      {[0, 1].map((leagueIdx) => (
        <div key={leagueIdx}>
          <Skeleton className="mb-2 h-3 w-32" />
          <div className="flex flex-col gap-3">
            {[0, 1, 2].map((divIdx) => (
              <div key={divIdx}>
                <Skeleton className="mb-1.5 h-3 w-16" />
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
                  {Array.from({ length: 5 }).map((_, i) => (
                    <div
                      key={i}
                      className="rounded-m border border-hairline-strong bg-white p-3.5"
                    >
                      <Skeleton className="mb-3 h-8 w-full" />
                      <Skeleton className="mb-1 h-3 w-full" />
                      <Skeleton className="h-3 w-2/3" />
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
