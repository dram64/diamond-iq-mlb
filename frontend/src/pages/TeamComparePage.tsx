import { useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';

import { Card } from '@/components/primitives/Card';
import { ErrorBanner } from '@/components/primitives/ErrorBanner';
import { Skeleton } from '@/components/primitives/Skeleton';
import { HexagonalRadar } from '@/components/comparison/HexagonalRadar';
import { TeamStatDetailTable } from '@/components/comparison/TeamStatDetailTable';
import { TEAM_RADAR_STATS } from '@/components/comparison/stat-extract';
import { useTeamCompare } from '@/hooks/useTeamCompare';
import { getAllMlbTeams, getMlbTeam } from '@/lib/mlbTeams';
import type { TeamStats } from '@/types/teamStats';

const DEFAULT_PAIR: readonly [number, number] = [147, 121]; // Yankees vs Mets

function parseIdsParam(raw: string | null): readonly number[] {
  if (!raw) return [];
  return raw
    .split(',')
    .map((s) => Number.parseInt(s.trim(), 10))
    .filter((n) => Number.isFinite(n) && n > 0);
}

export function TeamComparePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const idsFromUrl = useMemo(() => parseIdsParam(searchParams.get('ids')), [searchParams]);
  const ids = idsFromUrl.length === 2 ? idsFromUrl : DEFAULT_PAIR;
  const [idA, idB] = ids;

  const compare = useTeamCompare(ids);

  function setSlot(slot: 'a' | 'b', nextId: number) {
    const next = slot === 'a' ? [nextId, idB] : [idA, nextId];
    setSearchParams({ ids: next.join(',') });
  }

  const allTeams = getAllMlbTeams();

  return (
    <section className="page-data">
      <div className="kicker mb-2 text-accent-leather">Compare</div>
      <h1 className="display text-h1 text-paper-ink">Team Compare</h1>
      <p className="mt-1 max-w-2xl text-[13px] text-paper-ink-muted">
        Two MLB clubs, side by side. Hexagonal radar over six team-aggregate
        axes, with full numerical detail in the table below.
      </p>

      <div className="mt-7 rounded-l border border-hairline bg-surface-sunken/40 p-5">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <TeamSelect
            label="Team A"
            value={idA}
            otherValue={idB}
            options={allTeams}
            onChange={(id) => setSlot('a', id)}
          />
          <TeamSelect
            label="Team B"
            value={idB}
            otherValue={idA}
            options={allTeams}
            onChange={(id) => setSlot('b', id)}
          />
        </div>
      </div>

      <div className="mt-8">
        {compare.isLoading ? (
          <ComparePanelSkeleton />
        ) : compare.isError ? (
          <ErrorBanner
            title="Couldn't load comparison"
            message={compare.error?.message ?? 'Please try again in a moment.'}
            onRetry={() => void compare.refetch()}
          />
        ) : (
          <ComparePanel teams={compare.data?.data.teams ?? []} />
        )}
      </div>
    </section>
  );
}

interface TeamSelectProps {
  label: string;
  value: number;
  otherValue: number;
  options: readonly { id: number; abbreviation: string; fullName: string }[];
  onChange: (id: number) => void;
}

function TeamSelect({ label, value, otherValue, options, onChange }: TeamSelectProps) {
  const selected = options.find((t) => t.id === value);
  const meta = selected ? getMlbTeam(selected.id) : null;
  return (
    <label className="flex flex-col gap-2">
      <span className="kicker text-accent-leather">{label}</span>
      <div className="flex items-center gap-3 rounded-l border border-hairline-strong bg-surface-elevated px-3 py-2 shadow-sm transition-colors duration-200 ease-out focus-within:border-accent-leather">
        {meta ? (
          <img
            src={meta.logoPath}
            alt=""
            width={32}
            height={32}
            loading="lazy"
            className="h-8 w-8 shrink-0 object-contain"
          />
        ) : (
          <div className="h-8 w-8 shrink-0 rounded-full bg-surface-sunken" />
        )}
        <select
          value={value}
          onChange={(e) => onChange(Number.parseInt(e.target.value, 10))}
          className="flex-1 cursor-pointer border-0 bg-transparent text-[13.5px] font-bold text-paper-ink outline-none"
        >
          {options.map((t) => (
            <option key={t.id} value={t.id} disabled={t.id === otherValue}>
              {t.abbreviation} — {t.fullName}
            </option>
          ))}
        </select>
      </div>
    </label>
  );
}

interface ComparePanelProps {
  teams: readonly TeamStats[];
}

function ComparePanel({ teams }: ComparePanelProps) {
  if (teams.length < 2) {
    return (
      <Card>
        <div className="px-2 py-10 text-center text-[13px] text-paper-ink-soft">
          Comparison data unavailable.
        </div>
      </Card>
    );
  }

  const [a, b] = teams;
  return (
    <div className="flex flex-col gap-7">
      <Card className="overflow-hidden">
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
          <TeamSide team={a} accent />
          <TeamSide team={b} />
        </div>
      </Card>

      <div className="mx-auto w-full max-w-3xl">
        <HexagonalRadar
          stats={TEAM_RADAR_STATS}
          a={a}
          b={b}
          aName={a.team_name}
          bName={b.team_name}
        />
      </div>

      <TeamStatDetailTable teams={teams} />
    </div>
  );
}

function TeamSide({ team, accent = false }: { team: TeamStats; accent?: boolean }) {
  const meta = getMlbTeam(team.team_id);
  const games = (team.hitting?.games_played as number | undefined) ?? null;
  return (
    <div className="flex items-center gap-4">
      {meta ? (
        <img
          src={meta.logoPath}
          alt={meta.fullName}
          width={64}
          height={64}
          loading="lazy"
          className="h-16 w-16 shrink-0 object-contain"
        />
      ) : (
        <div className="h-16 w-16 shrink-0 rounded-full bg-surface-sunken" />
      )}
      <div className="flex flex-col gap-0.5">
        <div
          className={['kicker', accent ? 'text-accent-leather' : 'text-paper-ink-soft'].join(' ')}
        >
          {meta ? `${meta.league} ${meta.division}` : 'MLB'}
        </div>
        <div className="text-2xl font-bold -tracking-[0.01em] text-paper-ink">
          {team.team_name}
        </div>
        <div className="mono text-[11px] text-paper-ink-soft">
          {games ? `${games} games · ` : ''}Season {team.season}
        </div>
      </div>
    </div>
  );
}

function ComparePanelSkeleton() {
  return (
    <div className="flex flex-col gap-5">
      <Card>
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
          {[0, 1].map((i) => (
            <div key={i} className="flex items-center gap-4">
              <Skeleton className="h-16 w-16 rounded-full" />
              <div className="flex flex-col gap-1.5">
                <Skeleton className="h-3 w-20" />
                <Skeleton className="h-6 w-40" />
                <Skeleton className="h-3 w-32" />
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
