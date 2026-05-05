import { TeamChip } from '@/components/primitives/TeamChip';
import type { AppGame, AppTeam } from '@/types/app';

interface FinalsListProps {
  games: readonly AppGame[];
}

export function FinalsList({ games }: FinalsListProps) {
  if (games.length === 0) {
    return <EmptyState />;
  }
  const rows = games.slice(0, 5);

  return (
    <div className="grid grid-cols-5 gap-2.5">
      {rows.map((g) => {
        const awayWon = g.awayScore > g.homeScore;
        // Extra-inning final detection — backend's detailed_state usually has "Final" or similar.
        const note = /\bF\/(\d+)\b/.exec(g.detailedState)?.[0];
        return (
          <article
            key={g.id}
            className="flex flex-col gap-2 rounded-m border border-hairline-strong bg-white p-3.5 shadow-sm"
          >
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-bold uppercase tracking-[0.08em] text-paper-4">
                {note ?? 'Final'}
              </span>
            </div>
            <FinalTeamLine t={g.away} score={g.awayScore} won={awayWon} />
            <FinalTeamLine t={g.home} score={g.homeScore} won={!awayWon} />
          </article>
        );
      })}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="rounded-l border border-dashed border-hairline-strong bg-surface-2 px-4 py-6 text-center text-[12px] text-paper-4">
      No games have finished yet today.
    </div>
  );
}

function FinalTeamLine({
  t,
  score,
  won,
}: {
  t: AppTeam;
  score: number;
  won: boolean;
}) {
  return (
    <div className="flex items-center gap-2">
      <TeamChip abbr={t.abbreviation} color={t.primaryColor} logoPath={t.logoPath} size={20} />
      <span
        className={[
          'flex-1 text-[13px]',
          won ? 'font-bold text-paper' : 'font-medium text-paper-4',
        ].join(' ')}
      >
        {t.locationName || t.fullName}
      </span>
      <span
        className={[
          'mono text-base font-bold',
          won ? 'text-paper' : 'text-paper-4',
        ].join(' ')}
      >
        {score}
      </span>
    </div>
  );
}
