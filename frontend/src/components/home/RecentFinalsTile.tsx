import { Link } from 'react-router-dom';

import { Skeleton } from '@/components/primitives/Skeleton';
import { TeamChip } from '@/components/primitives/TeamChip';
import { useScoreboard } from '@/hooks/useScoreboard';
import type { AppGame } from '@/types/app';

const MAX_FINALS = 6;

export function RecentFinalsTile() {
  const { finalGames, isLoading, isError } = useScoreboard();

  // Most recent first — finalGames are sorted ascending by start_time;
  // reverse so the latest 6 surface.
  const recent = [...finalGames].reverse().slice(0, MAX_FINALS);

  return (
    <section
      aria-label="Recent final scores"
      className="flex flex-col gap-3 rounded-l border border-hairline-strong bg-surface-elevated p-5 shadow-sm"
    >
      <div className="flex items-baseline justify-between border-b border-hairline pb-2">
        <h3 className="text-[15px] font-bold tracking-[-0.005em] text-paper-ink">
          Recent Finals
        </h3>
        <span className="kicker text-paper-ink-soft">Latest {MAX_FINALS}</span>
      </div>

      {isLoading && <FinalsSkeleton />}
      {isError && <Empty message="Scores unavailable." />}
      {!isLoading && !isError && recent.length === 0 && (
        <Empty message="No finals yet." />
      )}
      {!isLoading && !isError && recent.length > 0 && (
        <div className="flex flex-col divide-y divide-hairline">
          {recent.map((g) => (
            <FinalRow key={g.id} game={g} />
          ))}
        </div>
      )}
    </section>
  );
}

function FinalRow({ game }: { game: AppGame }) {
  const awayWins = game.awayScore > game.homeScore;
  const homeWins = game.homeScore > game.awayScore;
  const target = `/compare-teams?ids=${game.away.id},${game.home.id}`;
  return (
    <Link
      to={target}
      className="grid grid-cols-[1fr_28px_1fr_auto] items-center gap-3 py-2.5 transition-colors duration-200 hover:bg-surface-sunken/60"
    >
      <TeamLine team={game.away} score={game.awayScore} winner={awayWins} alignRight />
      <span className="text-center text-[10px] font-semibold uppercase tracking-[0.06em] text-paper-ink-soft">
        @
      </span>
      <TeamLine team={game.home} score={game.homeScore} winner={homeWins} />
      <span className="kicker text-paper-ink-soft">F</span>
    </Link>
  );
}

function TeamLine({
  team,
  score,
  winner,
  alignRight = false,
}: {
  team: AppGame['away'] | AppGame['home'];
  score: number;
  winner: boolean;
  alignRight?: boolean;
}) {
  return (
    <div
      className={[
        'flex items-center gap-2',
        alignRight ? 'flex-row-reverse text-right' : '',
      ].join(' ')}
    >
      <TeamChip
        abbr={team.abbreviation}
        color={team.primaryColor}
        logoPath={team.logoPath}
        size={22}
      />
      <span
        className={[
          'truncate text-[12px]',
          winner ? 'font-bold text-paper-ink' : 'font-medium text-paper-ink-muted',
        ].join(' ')}
      >
        {team.abbreviation}
      </span>
      <span
        className={[
          'mono text-[14px]',
          winner ? 'font-bold text-paper-ink' : 'text-paper-ink-soft',
        ].join(' ')}
      >
        {score}
      </span>
    </div>
  );
}

function FinalsSkeleton() {
  return (
    <div className="flex flex-col divide-y divide-hairline">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="grid grid-cols-[1fr_28px_1fr_auto] items-center gap-3 py-2.5">
          <Skeleton className="h-5 w-full" />
          <Skeleton className="h-3 w-3" />
          <Skeleton className="h-5 w-full" />
          <Skeleton className="h-3 w-4" />
        </div>
      ))}
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
