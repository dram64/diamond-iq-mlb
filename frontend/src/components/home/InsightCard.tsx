import type { AIInsight } from '@/types';

interface InsightCardProps {
  insight: AIInsight;
}

export function InsightCard({ insight }: InsightCardProps) {
  return (
    <article className="flex flex-col gap-2 rounded-l border border-hairline-strong bg-white p-4 shadow-sm">
      <div className="flex items-center justify-between">
        <span className="inline-flex items-center gap-1.5 rounded-s bg-accent-wash px-1.5 py-0.5 text-[9.5px] font-bold uppercase tracking-[0.08em] text-accent">
          AI Insight
        </span>
        <span className="mono text-[10px] text-paper-4">{insight.tag}</span>
      </div>
      <h4 className="text-sm">{insight.topic}</h4>
      <p className="m-0 text-[13px] leading-relaxed text-paper-3">{insight.blurb}</p>
      <button
        type="button"
        className="mt-0.5 self-start bg-transparent p-0 text-xs font-semibold text-accent hover:text-accent-glow"
      >
        Ask Diamond IQ →
      </button>
    </article>
  );
}
