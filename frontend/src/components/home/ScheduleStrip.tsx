import { TeamChip } from '@/components/primitives/TeamChip';
import type { AppGame } from '@/types/app';

interface ScheduleStripProps {
  games: readonly AppGame[];
}

const EMDASH = '—';

export function ScheduleStrip({ games }: ScheduleStripProps) {
  if (games.length === 0) {
    return (
      <div className="rounded-l border border-dashed border-hairline-strong bg-surface-2 px-4 py-6 text-center text-[12px] text-paper-4">
        No upcoming games.
      </div>
    );
  }

  // Show up to 6 in the strip; layout fixed at 6 columns for visual balance.
  const visible = games.slice(0, 6);
  return (
    <div className="grid grid-cols-6 gap-2.5">
      {visible.map((g) => {
        const localTime = formatLocalTime(g.startTimeUtc);
        return (
          <article
            key={g.id}
            className="flex flex-col gap-2.5 rounded-m border border-hairline-strong bg-white p-3 shadow-sm"
          >
            <div className="mono text-[11px] font-bold text-paper-2">{localTime}</div>
            <div className="flex flex-col gap-1.5">
              <div className="flex items-center gap-2">
                <TeamChip abbr={g.away.abbreviation} color={g.away.primaryColor} logoPath={g.away.logoPath} size={22} />
                <span className="text-[13px] font-semibold">{g.away.abbreviation}</span>
              </div>
              <div className="text-[9px] tracking-[0.08em] text-paper-5">@</div>
              <div className="flex items-center gap-2">
                <TeamChip abbr={g.home.abbreviation} color={g.home.primaryColor} logoPath={g.home.logoPath} size={22} />
                <span className="text-[13px] font-semibold">{g.home.abbreviation}</span>
              </div>
            </div>
            {/* Probable pitchers — backend doesn't supply yet, so render the line as a placeholder. */}
            <div className="border-t border-hairline pt-2 text-[10px] leading-tight text-paper-4">
              <div>{EMDASH}</div>
              <div>{EMDASH}</div>
            </div>
          </article>
        );
      })}
    </div>
  );
}

function formatLocalTime(iso: string): string {
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return EMDASH;
    return d.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });
  } catch {
    return EMDASH;
  }
}
