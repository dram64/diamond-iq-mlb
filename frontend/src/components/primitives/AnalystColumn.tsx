import type { ReactNode } from 'react';

interface AnalystColumnProps {
  children: ReactNode;
  topic: string;
  byline?: string;
  ts?: string;
  /** Compact variant tightens padding and reduces headline size. */
  compact?: boolean;
}

/**
 * AI analyst "beat writer" card — kicker + topic headline + body + byline row
 * with an "Ask Diamond IQ" CTA. Used on live game, player, and team screens.
 */
export function AnalystColumn({
  children,
  topic,
  byline = 'The Beat',
  ts = 'updated just now',
  compact = false,
}: AnalystColumnProps) {
  return (
    <aside
      className={[
        'fade-in flex flex-col gap-3 rounded-l border border-hairline-strong bg-surface-1 shadow-sm',
        compact ? 'px-5 py-4' : 'px-6 py-5',
      ].join(' ')}
    >
      <div className="flex items-center gap-2">
        <span className="inline-flex items-center gap-1.5 rounded-s bg-accent-wash px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.08em] text-accent">
          AI Analyst
        </span>
        <span className="text-[11px] text-paper-4">{ts}</span>
      </div>
      <h3 className={compact ? 'text-base leading-tight' : 'text-xl leading-tight'}>
        {topic}
      </h3>
      <div
        className={[
          'text-paper-3',
          compact ? 'text-[13.5px] leading-relaxed' : 'text-[14.5px] leading-relaxed',
        ].join(' ')}
      >
        {children}
      </div>
      <div className="flex items-center gap-2 border-t border-hairline pt-2.5 text-[11px] text-paper-4">
        <span>
          Analysis by{' '}
          <span className="font-semibold text-paper-2">{byline}</span>
        </span>
        <button
          type="button"
          className="ml-auto rounded-m bg-accent px-3 py-1.5 font-sans text-[11px] font-semibold text-white hover:bg-accent-glow"
        >
          Ask Diamond IQ
        </button>
      </div>
    </aside>
  );
}
