import type { Count } from '@/types';

interface CountPipsProps {
  count: Count;
  outs: number;
}

/** B / S / O pip grid — balls/strikes in accent, outs in live red. */
export function CountPips({ count, outs }: CountPipsProps) {
  return (
    <div className="grid grid-cols-[auto_1fr] items-center gap-x-2.5 gap-y-1">
      <PipLabel>B</PipLabel>
      <PipRow value={count.balls} max={3} />
      <PipLabel>S</PipLabel>
      <PipRow value={count.strikes} max={2} />
      <PipLabel>O</PipLabel>
      <PipRow value={outs} max={2} tone="live" />
    </div>
  );
}

function PipLabel({ children }: { children: string }) {
  return (
    <span className="kicker text-[9px]" aria-hidden="true">
      {children}
    </span>
  );
}

function PipRow({
  value,
  max,
  tone = 'accent',
}: {
  value: number;
  max: number;
  tone?: 'accent' | 'live';
}) {
  const onColor = tone === 'live' ? 'bg-live' : 'bg-accent';
  const onBorder = tone === 'live' ? 'border-live' : 'border-accent';
  return (
    <div className="flex gap-1">
      {Array.from({ length: max }).map((_, i) => {
        const on = i < value;
        return (
          <span
            key={i}
            className={[
              'h-2 w-2 rounded-full border',
              on
                ? `${onColor} ${onBorder}`
                : 'border-surface-3 bg-transparent',
            ].join(' ')}
          />
        );
      })}
    </div>
  );
}
