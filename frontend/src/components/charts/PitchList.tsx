import type { Pitch } from '@/types';

interface PitchListProps {
  pitches: readonly Pitch[];
}

/** Tabular list of pitches — number, type, velocity, result. Meant to sit under StrikeZone. */
export function PitchList({ pitches }: PitchListProps) {
  return (
    <ul className="flex flex-col">
      {pitches.map((p, i) => {
        const isLast = i === pitches.length - 1;
        return (
          <li
            key={p.n}
            className={[
              'grid grid-cols-[18px_34px_44px_1fr] items-center gap-2.5 py-1.5',
              'mono text-[11px] text-paper-2',
              isLast ? '' : 'border-b border-hairline',
            ].join(' ')}
          >
            <span className="text-paper-5">P{p.n}</span>
            <span className="text-accent-glow">{p.type}</span>
            <span>{p.mph.toFixed(1)}</span>
            <span className="capitalize text-paper-3">{p.result}</span>
          </li>
        );
      })}
    </ul>
  );
}
