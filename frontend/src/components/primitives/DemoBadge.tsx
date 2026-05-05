import { HIDE_DEMO_BADGES } from '@/lib/env';

/**
 * Tiny "Demo data" badge for sections still backed by mock data while
 * the backend doesn't yet serve the relevant endpoint. Suppressed when
 * `VITE_HIDE_DEMO_BADGES=true` for clean screenshots.
 */
export function DemoBadge() {
  if (HIDE_DEMO_BADGES) return null;
  return (
    <span
      className="inline-flex items-center rounded-s border border-hairline-strong bg-surface-2 px-1.5 py-0.5 text-[9.5px] font-semibold uppercase tracking-[0.08em] text-paper-4"
      title="This section uses placeholder data; the backend doesn't serve it yet."
    >
      Demo data
    </span>
  );
}
