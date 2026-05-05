import type { PlayerAwardsBlock } from '@/types/compare';

interface AccoladesRowProps {
  awards: PlayerAwardsBlock | null | undefined;
  /** Optional className for layout tweaks at the call site. */
  className?: string;
}

interface ChipSpec {
  label: string;
  count: number;
  years: number[];
  /** Pico-tone hex color for the chip border + text. */
  color: string;
}

function buildChips(a: PlayerAwardsBlock): ChipSpec[] {
  const out: ChipSpec[] = [];
  if (a.mvp_count > 0) out.push({ label: 'MVP', count: a.mvp_count, years: a.mvp_years, color: '#b45309' });
  if (a.cy_young_count > 0) out.push({ label: 'CY', count: a.cy_young_count, years: a.cy_young_years, color: '#7c3aed' });
  if (a.rookie_of_the_year_count > 0) out.push({ label: 'ROY', count: a.rookie_of_the_year_count, years: a.rookie_of_the_year_years, color: '#0e7490' });
  if (a.world_series_count > 0) out.push({ label: 'WS', count: a.world_series_count, years: a.world_series_years, color: '#b91c1c' });
  if (a.all_star_count > 0) out.push({ label: 'AS', count: a.all_star_count, years: a.all_star_years, color: '#1d4ed8' });
  if (a.gold_glove_count > 0) out.push({ label: 'GG', count: a.gold_glove_count, years: a.gold_glove_years, color: '#a16207' });
  if (a.silver_slugger_count > 0) out.push({ label: 'SS', count: a.silver_slugger_count, years: a.silver_slugger_years, color: '#475569' });
  return out;
}

export function AccoladesRow({ awards, className = '' }: AccoladesRowProps) {
  if (!awards) return null;
  const chips = buildChips(awards);
  if (chips.length === 0) return null;

  return (
    <div className={['flex flex-wrap gap-1.5', className].join(' ')} aria-label="Career accolades">
      {chips.map((c) => (
        <span
          key={c.label}
          title={`${c.label} · ${c.count} (${c.years.join(', ')})`}
          className="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10.5px] font-bold"
          style={{ borderColor: c.color, color: c.color }}
        >
          <span>{c.label}</span>
          <span className="mono text-[10px]">×{c.count}</span>
        </span>
      ))}
    </div>
  );
}
