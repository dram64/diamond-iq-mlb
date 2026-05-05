import { Navigate, useParams, Link } from 'react-router-dom';

import { Card } from '@/components/primitives/Card';
import { ErrorBanner } from '@/components/primitives/ErrorBanner';
import { Skeleton } from '@/components/primitives/Skeleton';
import { PlayerHeadshot } from '@/components/PlayerHeadshot';
import { useRoster } from '@/hooks/useRoster';
import { useStandings } from '@/hooks/useStandings';
import { useTeamStats } from '@/hooks/useTeamStats';
import { getMlbTeam } from '@/lib/mlbTeams';
import { MLB_DIVISIONS } from '@/lib/mlbDivisions';
import type { StandingsRecord } from '@/types/standings';

const HITTING_STATS: Array<{ token: string; label: string }> = [
  { token: 'avg', label: 'AVG' },
  { token: 'home_runs', label: 'HR' },
  { token: 'rbi', label: 'RBI' },
  { token: 'obp', label: 'OBP' },
  { token: 'slg', label: 'SLG' },
  { token: 'ops', label: 'OPS' },
  { token: 'stolen_bases', label: 'SB' },
  { token: 'runs', label: 'R' },
];

const PITCHING_STATS: Array<{ token: string; label: string }> = [
  { token: 'era', label: 'ERA' },
  { token: 'whip', label: 'WHIP' },
  { token: 'strikeouts', label: 'K' },
  { token: 'wins', label: 'W' },
  { token: 'losses', label: 'L' },
  { token: 'saves', label: 'SV' },
  { token: 'opp_avg', label: 'OPP AVG' },
  { token: 'innings_pitched', label: 'IP' },
];

export function TeamDetailPage() {
  const { teamId: raw } = useParams<{ teamId: string }>();
  const teamId = raw ? Number.parseInt(raw, 10) : NaN;
  const valid = Number.isFinite(teamId);

  const stats = useTeamStats(valid ? teamId : null);
  const roster = useRoster(valid ? teamId : null);
  const standings = useStandings();

  if (!valid) return <Navigate to="/teams" replace />;

  const meta = getMlbTeam(teamId);
  const standingsRow = standings.data?.data.teams.find((t) => t.team_id === teamId);
  const division = MLB_DIVISIONS.find(
    (d) => d.league === meta?.league && d.abbr.endsWith(meta?.division ?? ''),
  );

  return (
    <section>
      <NavyHeaderBand
        teamFullName={meta?.fullName ?? `Team ${teamId}`}
        teamLogoPath={meta?.logoPath}
        divisionLabel={
          standingsRow && division
            ? `${division.abbr} · #${standingsRow.division_rank}`
            : division?.abbr ?? null
        }
        standings={standingsRow}
        standingsLoading={standings.isLoading}
      />

      <div className="page-data">
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Card>
            <div className="kicker mb-3 text-paper-ink-soft">Team batting</div>
            {stats.isLoading ? (
              <StatsSkeleton />
            ) : stats.isError ? (
              <ErrorBanner
                title="Stats unavailable"
                message={stats.error?.message ?? 'Try again shortly.'}
                onRetry={() => void stats.refetch()}
              />
            ) : (
              <StatGrid stats={stats.data?.data.hitting} rows={HITTING_STATS} />
            )}
          </Card>
          <Card>
            <div className="kicker mb-3 text-paper-ink-soft">Team pitching</div>
            {stats.isLoading ? (
              <StatsSkeleton />
            ) : stats.isError ? null : (
              <StatGrid stats={stats.data?.data.pitching} rows={PITCHING_STATS} />
            )}
          </Card>
        </div>

        <Card className="mt-5">
          <div className="kicker mb-3 text-paper-ink-soft">Active roster</div>
          {roster.isLoading ? (
            <RosterSkeleton />
          ) : roster.isError ? (
            <ErrorBanner
              title="Couldn't load roster"
              message={roster.error?.message ?? 'Try again shortly.'}
              onRetry={() => void roster.refetch()}
            />
          ) : (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
              {(roster.data?.data.roster ?? []).map((p) => (
                <Link
                  key={p.person_id}
                  to={`/compare-players?ids=${p.person_id}`}
                  className="group flex items-center gap-3 rounded-m border border-hairline bg-surface-sunken/60 px-3 py-2 hover:border-accent-leather"
                >
                  <PlayerHeadshot
                    playerId={p.person_id}
                    playerName={p.full_name}
                    size="sm"
                  />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-[12.5px] font-semibold text-paper-ink group-hover:text-accent-leather">
                      {p.full_name}
                    </div>
                    <div className="mono text-[10.5px] text-paper-ink-soft">
                      {p.position_abbr}
                      {p.jersey_number ? ` · #${p.jersey_number}` : ''}
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </Card>
      </div>
    </section>
  );
}

interface NavyHeaderBandProps {
  teamFullName: string;
  teamLogoPath: string | undefined;
  divisionLabel: string | null;
  standings: StandingsRecord | undefined;
  standingsLoading: boolean;
}

function NavyHeaderBand({
  teamFullName,
  teamLogoPath,
  divisionLabel,
  standings,
  standingsLoading,
}: NavyHeaderBandProps) {
  return (
    <div className="band-navy -mx-6 mb-8 border-b border-accent-gold/20 px-6 py-8 md:-mx-10 md:px-10 md:py-10">
      <div className="grid grid-cols-1 items-center gap-6 md:grid-cols-[auto_1fr_auto] md:gap-10">
        {teamLogoPath ? (
          <img
            src={teamLogoPath}
            alt={teamFullName}
            width={100}
            height={100}
            loading="lazy"
            className="h-[100px] w-[100px] shrink-0 object-contain drop-shadow-[0_2px_8px_rgba(0,0,0,0.35)]"
          />
        ) : (
          <div className="h-[100px] w-[100px] shrink-0 rounded-full bg-paper-cream/10" />
        )}

        <div className="flex min-w-0 flex-col gap-1.5">
          <span className="kicker text-paper-cream-2">{divisionLabel ?? 'MLB'}</span>
          <h1 className="display text-[34px] leading-tight text-paper-cream md:text-[42px]">
            {teamFullName}
          </h1>
          <span className="mono text-[12px] text-paper-cream-2">
            {standingsLoading
              ? 'Loading…'
              : standings?.pct
                ? `${standings.pct} win pct`
                : '—'}
          </span>
        </div>

        <div className="flex flex-col items-start gap-3 md:items-end">
          {standingsLoading ? (
            <Skeleton className="h-12 w-32 bg-paper-cream/15" />
          ) : standings ? (
            <>
              <div className="display flex items-baseline gap-3 text-paper-cream">
                <span className="text-[44px] leading-none">{standings.wins}</span>
                <span className="text-[26px] leading-none text-paper-cream-2">–</span>
                <span className="text-[44px] leading-none">{standings.losses}</span>
              </div>
              <div className="mono text-[12.5px] text-paper-cream-2">
                <span className="font-semibold">
                  {standings.run_differential >= 0 ? '+' : ''}
                  {standings.run_differential}
                </span>{' '}
                run differential
                {standings.games_back && standings.games_back !== '-' && (
                  <span> · {standings.games_back} GB</span>
                )}
              </div>
            </>
          ) : (
            <span className="mono text-[13px] text-paper-cream-2">—</span>
          )}
        </div>
      </div>
    </div>
  );
}

function StatGrid({
  stats,
  rows,
}: {
  stats: Record<string, unknown> | null | undefined;
  rows: Array<{ token: string; label: string }>;
}) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {rows.map((r) => {
        const v = stats?.[r.token];
        const display =
          v === null || v === undefined || v === ''
            ? '—'
            : typeof v === 'number'
              ? Number.isInteger(v)
                ? v.toString()
                : v.toFixed(2)
              : String(v);
        return (
          <div key={r.token} className="flex flex-col">
            <span className="kicker text-[10px] text-paper-ink-soft">{r.label}</span>
            <span className="mono text-[15px] font-bold text-paper-ink">{display}</span>
          </div>
        );
      })}
    </div>
  );
}

function StatsSkeleton() {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {Array.from({ length: 8 }).map((_, i) => (
        <div key={i}>
          <Skeleton className="mb-1 h-3 w-12" />
          <Skeleton className="h-5 w-16" />
        </div>
      ))}
    </div>
  );
}

function RosterSkeleton() {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
      {Array.from({ length: 25 }).map((_, i) => (
        <div
          key={i}
          className="flex items-center gap-3 rounded-m border border-hairline bg-surface-sunken/60 px-3 py-2"
        >
          <Skeleton className="h-8 w-8 rounded-full" />
          <div className="flex-1">
            <Skeleton className="mb-1 h-3 w-20" />
            <Skeleton className="h-3 w-12" />
          </div>
        </div>
      ))}
    </div>
  );
}
