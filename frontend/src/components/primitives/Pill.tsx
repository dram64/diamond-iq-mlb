import type { ReactNode } from 'react';

export type PillTone = 'default' | 'live' | 'accent' | 'good' | 'bad';

interface PillProps {
  tone?: PillTone;
  children: ReactNode;
}

const TONE_CLASSES: Record<PillTone, string> = {
  default: 'bg-surface-2 text-paper-3 border-hairline-strong',
  live:    'bg-live-soft text-live border-transparent',
  accent:  'bg-accent-wash text-accent border-transparent',
  good:    'bg-good/10 text-good border-transparent',
  bad:     'bg-bad/10 text-bad border-transparent',
};

export function Pill({ tone = 'default', children }: PillProps) {
  return (
    <span
      className={[
        'inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5',
        'font-sans text-[10.5px] font-semibold uppercase tracking-[0.04em]',
        TONE_CLASSES[tone],
      ].join(' ')}
    >
      {children}
    </span>
  );
}
