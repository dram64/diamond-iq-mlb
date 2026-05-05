import { Link } from 'react-router-dom';

import { Skeleton } from '@/components/primitives/Skeleton';
import { useFeaturedGame } from '@/hooks/useFeaturedGame';
import { getMlbTeam } from '@/lib/mlbTeams';
import type { FeaturedGameTeam } from '@/types/featuredGame';

const STATUS_LABEL: Record<string, string> = {
  preview: 'Today',
  scheduled: 'Today',
  live: 'Live',
  final: 'Final',
  postponed: 'Postponed',
};

export function FeaturedMatchupHero() {
  const { data, isLoading, isError, error } = useFeaturedGame();

  if (isLoading) return <HeroSkeleton />;

  if (isError) {
    const offDay = error?.code === 'off_day' || error?.code === 'data_not_yet_available';
    if (offDay) return <OffDayBanner code={error?.code ?? null} />;
    return (
      <section className="rounded-l border border-hairline-strong bg-surface-elevated p-7 text-center text-[13px] text-paper-ink-soft">
        Couldn't load today's featured game.
      </section>
    );
  }

  const game = data?.data;
  if (!game) return <OffDayBanner code={null} />;

  const target = `/compare-teams?ids=${game.away.team_id},${game.home.team_id}`;
  const startLabel = formatStartTime(game.start_time_utc);
  const statusLabel = STATUS_LABEL[game.status] ?? game.detailed_state ?? 'Today';
  const showProbables =
    (game.status === 'preview' || game.status === 'scheduled') &&
    (game.away.probable_pitcher !== null || game.home.probable_pitcher !== null);

  return (
    <section
      aria-label="Today's featured game"
      className="relative overflow-hidden rounded-l border border-hairline-strong bg-surface-elevated shadow-md"
    >
      <div className="flex items-center justify-between border-b border-hairline px-7 py-3">
        <span className="kicker text-accent-leather">Featured Game · {statusLabel}</span>
        <span className="mono text-[10.5px] text-paper-ink-soft">
          {game.date}
          {game.venue ? ` · ${game.venue}` : ''}
          {startLabel ? ` · ${startLabel}` : ''}
        </span>
      </div>

      <div className="grid grid-cols-1 items-center gap-10 px-7 py-10 md:grid-cols-[1fr_auto_1fr] md:gap-6 md:py-12">
        <HeroTeamSide team={game.away} alignRight={false} kicker="Away" />
        <div className="hidden text-center md:block">
          <span className="display text-[40px] leading-none text-paper-ink-soft">@</span>
        </div>
        <HeroTeamSide team={game.home} alignRight kicker="Home" />
      </div>

      {showProbables && (
        <div className="border-t border-hairline bg-surface-sunken/40 px-7 py-3">
          <div className="kicker mb-1 text-paper-ink-soft">Probable starters</div>
          <div className="flex flex-wrap items-center justify-between gap-4 text-[12.5px] text-paper-ink-muted">
            <ProbableLine label={getTeamShort(game.away)} pitcher={game.away.probable_pitcher} />
            <span className="mono text-[11px] text-paper-ink-soft">vs</span>
            <ProbableLine label={getTeamShort(game.home)} pitcher={game.home.probable_pitcher} />
          </div>
        </div>
      )}

      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-hairline bg-surface-sunken/60 px-7 py-3.5">
        <span className="text-[12.5px] text-paper-ink-muted">
          Side-by-side team stats, run differential, and analysis.
        </span>
        <Link
          to={target}
          className="group inline-flex items-center gap-1.5 rounded-m border border-accent-gold/40 bg-accent-gold/15 px-4 py-1.5 text-[12.5px] font-bold text-accent-leather transition-colors duration-200 ease-out hover:border-accent-gold hover:bg-accent-gold/25"
          aria-label={`Compare ${game.away.team_name} vs ${game.home.team_name}`}
        >
          View comparison
          <span className="text-accent-gold transition-transform duration-200 ease-out group-hover:translate-x-0.5">
            →
          </span>
        </Link>
      </div>
    </section>
  );
}

interface HeroTeamSideProps {
  team: FeaturedGameTeam;
  alignRight: boolean;
  kicker: string;
}

function HeroTeamSide({ team, alignRight, kicker }: HeroTeamSideProps) {
  const meta = getMlbTeam(team.team_id);
  return (
    <div
      className={[
        'flex items-center gap-6',
        alignRight ? 'md:flex-row-reverse md:text-right' : '',
      ].join(' ')}
    >
      {meta ? (
        <img
          src={meta.logoPath}
          alt={meta.fullName}
          width={120}
          height={120}
          loading="lazy"
          className="h-[120px] w-[120px] shrink-0 object-contain"
        />
      ) : (
        <div className="h-[120px] w-[120px] shrink-0 rounded-full bg-surface-sunken" />
      )}
      <div className={['flex min-w-0 flex-col gap-2', alignRight ? 'md:items-end' : ''].join(' ')}>
        <span className="kicker text-accent-leather">{kicker}</span>
        <h2 className="display text-[28px] leading-tight text-paper-ink md:text-[32px]">
          {meta?.fullName ?? team.team_name}
        </h2>
        <div className="display flex items-baseline gap-3 text-paper-ink">
          <span className="text-[44px] leading-none">{team.wins}</span>
          <span className="text-[26px] leading-none text-paper-ink-soft">–</span>
          <span className="text-[44px] leading-none">{team.losses}</span>
        </div>
        {team.run_differential !== null && (
          <div className="mono text-[12px] text-paper-ink-muted">
            <span className="font-semibold">
              {team.run_differential >= 0 ? '+' : ''}
              {team.run_differential}
            </span>{' '}
            run differential
          </div>
        )}
      </div>
    </div>
  );
}

function ProbableLine({
  label,
  pitcher,
}: {
  label: string;
  pitcher: FeaturedGameTeam['probable_pitcher'];
}) {
  return (
    <span className="flex items-baseline gap-2">
      <span className="kicker text-accent-leather">{label}</span>
      <span className="mono text-[12.5px] font-semibold text-paper-ink">
        {pitcher?.full_name ?? 'TBD'}
      </span>
    </span>
  );
}

function OffDayBanner({ code }: { code: string | null }) {
  const isHiccup = code === 'data_not_yet_available';
  return (
    <section
      aria-label="MLB off-day"
      className="overflow-hidden rounded-l border border-hairline-strong bg-surface-elevated shadow-sm"
    >
      <div className="border-b border-hairline px-7 py-3">
        <span className="kicker text-accent-leather">MLB Off-Day</span>
      </div>
      <div className="px-7 py-12 text-center">
        <h2 className="display text-[28px] leading-tight text-paper-ink md:text-[32px]">
          {isHiccup ? 'Schedule unavailable right now' : 'No games scheduled today'}
        </h2>
        <p className="mt-3 text-[13px] text-paper-ink-muted">
          {isHiccup
            ? 'The MLB schedule feed hiccupped. Try again in a moment.'
            : 'Back tomorrow with the full slate. In the meantime, browse standings and team pages below.'}
        </p>
        <Link
          to="/teams"
          className="mt-6 inline-flex items-center gap-1.5 rounded-m border border-accent-gold/40 bg-accent-gold/15 px-4 py-1.5 text-[12.5px] font-bold text-accent-leather transition-colors duration-200 ease-out hover:border-accent-gold hover:bg-accent-gold/25"
        >
          Browse teams
          <span className="text-accent-gold">→</span>
        </Link>
      </div>
    </section>
  );
}

function HeroSkeleton() {
  return (
    <section className="rounded-l border border-hairline-strong bg-surface-elevated p-7 shadow-md">
      <Skeleton className="mb-6 h-3 w-56" />
      <div className="grid grid-cols-1 items-center gap-10 py-6 md:grid-cols-[1fr_auto_1fr]">
        {[0, 1].map((i) => (
          <div key={i} className="flex items-center gap-6">
            <Skeleton className="h-[120px] w-[120px]" />
            <div className="flex flex-col gap-3">
              <Skeleton className="h-3 w-20" />
              <Skeleton className="h-7 w-48" />
              <Skeleton className="h-10 w-32" />
              <Skeleton className="h-3 w-40" />
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function getTeamShort(team: FeaturedGameTeam): string {
  return team.abbreviation || team.team_name;
}

function formatStartTime(iso: string): string {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '';
    return d.toLocaleTimeString(undefined, {
      hour: 'numeric',
      minute: '2-digit',
      timeZoneName: 'short',
    });
  } catch {
    return '';
  }
}
