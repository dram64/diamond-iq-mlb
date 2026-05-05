import { Link } from 'react-router-dom';

import { Skeleton } from '@/components/primitives/Skeleton';
import { useStandings } from '@/hooks/useStandings';
import { MLB_DIVISIONS, type MlbDivision } from '@/lib/mlbDivisions';
import { getAllMlbTeams, type MlbTeam } from '@/lib/mlbTeams';
import type { StandingsRecord } from '@/types/standings';

export function TeamsPage() {
  const { data, isLoading } = useStandings();
  const standingsByTeam: ReadonlyMap<number, StandingsRecord> = new Map(
    (data?.data.teams ?? []).map((t) => [t.team_id, t]),
  );

  return (
    <section className="page-data">
      <div className="kicker mb-2 text-accent-leather">Teams</div>
      <h1 className="display text-h1 text-paper-ink">All 30 Clubs</h1>
      <p className="mt-1 max-w-2xl text-[13px] text-paper-ink-muted">
        Every MLB club, grouped by division. Tap a team for roster, season aggregates, and
        recent record.
      </p>

      <div className="mt-8 flex flex-col gap-9">
        {MLB_DIVISIONS.map((division) => {
          const teams = getAllMlbTeams().filter(
            (t) => t.league === division.league && divisionWord(division) === t.division,
          );
          return (
            <DivisionBlock
              key={division.id}
              division={division}
              teams={teams}
              standingsByTeam={standingsByTeam}
              isLoading={isLoading}
            />
          );
        })}
      </div>
    </section>
  );
}

function divisionWord(d: MlbDivision): 'East' | 'Central' | 'West' {
  if (d.abbr.endsWith('East')) return 'East';
  if (d.abbr.endsWith('Central')) return 'Central';
  return 'West';
}

interface DivisionBlockProps {
  division: MlbDivision;
  teams: readonly MlbTeam[];
  standingsByTeam: ReadonlyMap<number, StandingsRecord>;
  isLoading: boolean;
}

function DivisionBlock({ division, teams, standingsByTeam, isLoading }: DivisionBlockProps) {
  // Order teams by division_rank when standings have arrived; otherwise
  // keep the static catalog order. Either is meaningful — but a leader-
  // first arrangement reads more naturally on the standings-aware grid.
  const ordered = standingsByTeam.size > 0
    ? [...teams].sort((a, b) => {
        const ra = standingsByTeam.get(a.id)?.division_rank ?? 999;
        const rb = standingsByTeam.get(b.id)?.division_rank ?? 999;
        return ra - rb;
      })
    : teams;

  return (
    <div>
      <div className="mb-4 flex items-baseline justify-between border-b border-hairline pb-2">
        <span className="kicker text-accent-leather">{division.abbr}</span>
        <span className="kicker text-paper-ink-soft">{division.league} · {division.name.split(' ').pop()}</span>
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-5">
        {ordered.map((t) => (
          <TeamTile
            key={t.id}
            team={t}
            standings={standingsByTeam.get(t.id)}
            isLoading={isLoading}
          />
        ))}
      </div>
    </div>
  );
}

interface TeamTileProps {
  team: MlbTeam;
  standings?: StandingsRecord;
  isLoading: boolean;
}

function TeamTile({ team, standings, isLoading }: TeamTileProps) {
  return (
    <Link
      to={`/teams/${team.id}`}
      className="group relative flex flex-col items-center gap-2.5 rounded-l border border-hairline-strong bg-surface-elevated px-4 py-5 shadow-sm transition-all duration-200 ease-out hover:-translate-y-0.5 hover:border-accent-gold/60 hover:shadow-md"
      aria-label={`${team.fullName}${standings ? ` — ${standings.wins}-${standings.losses}` : ''}`}
    >
      {/* Corner W-L badge */}
      <div className="absolute right-2 top-2">
        {isLoading ? (
          <Skeleton className="h-4 w-12" />
        ) : standings ? (
          <span className="rounded-s border border-hairline bg-surface-sunken/70 px-1.5 py-0.5 text-[10px] font-bold tracking-tight text-paper-ink mono">
            {standings.wins}-{standings.losses}
          </span>
        ) : null}
      </div>

      <img
        src={team.logoPath}
        alt={team.fullName}
        width={80}
        height={80}
        loading="lazy"
        className="h-20 w-20 shrink-0 object-contain transition-transform duration-200 ease-out group-hover:scale-[1.04]"
      />
      <div className="flex flex-col items-center gap-0.5 text-center">
        <div className="text-[13px] font-bold leading-tight text-paper-ink">{team.teamName}</div>
        <div className="mono text-[10px] uppercase tracking-[0.06em] text-paper-ink-soft">
          {team.abbreviation}
        </div>
        {!isLoading && standings && standings.games_back && standings.games_back !== '-' && (
          <div className="mono text-[10.5px] text-paper-ink-soft">{standings.games_back} GB</div>
        )}
      </div>
    </Link>
  );
}
