import { StatusChip } from './StatusChip';

interface DateStripProps {
  live: number;
  finals: number;
  upcoming: number;
}

export function DateStrip({ live, finals, upcoming }: DateStripProps) {
  return (
    <div className="flex items-center justify-between">
      <div>
        <div className="text-[11px] font-semibold uppercase tracking-[0.06em] text-paper-4">
          {formatToday()}
        </div>
        <h1 className="mt-1.5 text-[28px]">Scoreboard</h1>
      </div>
      <div className="flex gap-2">
        <StatusChip count={live} label="Live" tone="live" />
        <StatusChip count={upcoming} label="Scheduled" />
        <StatusChip count={finals} label="Final" />
      </div>
    </div>
  );
}

function formatToday(): string {
  const d = new Date();
  return d.toLocaleDateString(undefined, {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  });
}
