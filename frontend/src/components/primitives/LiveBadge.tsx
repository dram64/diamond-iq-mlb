interface LiveBadgeProps {
  count: number;
}

export function LiveBadge({ count }: LiveBadgeProps) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded bg-live px-2 py-0.5 text-[10.5px] font-bold uppercase tracking-[0.08em] text-white">
      <span className="h-1.5 w-1.5 animate-livepulse rounded-full bg-white" />
      <span className="whitespace-nowrap">Live · {count}</span>
    </span>
  );
}
