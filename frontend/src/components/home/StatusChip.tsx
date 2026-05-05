type Tone = 'live' | 'default';

interface StatusChipProps {
  count: number;
  label: string;
  tone?: Tone;
}

export function StatusChip({ count, label, tone = 'default' }: StatusChipProps) {
  const isLive = tone === 'live';
  return (
    <div
      className={[
        'flex items-center gap-2 rounded-m px-3 py-2',
        isLive
          ? 'border border-transparent bg-live-soft'
          : 'border border-hairline-strong bg-surface-1',
      ].join(' ')}
    >
      {isLive && <span className="live-dot" />}
      <span
        className={[
          'mono text-base font-bold',
          isLive ? 'text-live' : 'text-paper',
        ].join(' ')}
      >
        {count}
      </span>
      <span
        className={[
          'text-[11px] font-semibold uppercase tracking-[0.04em]',
          isLive ? 'text-live' : 'text-paper-4',
        ].join(' ')}
      >
        {label}
      </span>
    </div>
  );
}
