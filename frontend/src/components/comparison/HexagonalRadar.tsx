import { useState } from 'react';

interface RadarStatRef<T> {
  label: string;
  token: string;
  ascending?: boolean;
  pick: (subject: T) => number | null;
  format: (v: number | null) => string;
  percentileBaseline?: { p10: number; p90: number };
}

interface HexagonalRadarProps<T> {
  /** Six axes, in clockwise order from the top. */
  stats: readonly RadarStatRef<T>[];
  a: T;
  b: T;
  /** Display name for legend + caption strip. */
  aName: string;
  bName: string;
}

const SIZE = 460;
const CENTER = SIZE / 2;
const MAX_RADIUS = 168;

function vertex(index: number, fraction: number, axisCount: number) {
  const angleDeg = -90 + index * (360 / axisCount);
  const angleRad = (angleDeg * Math.PI) / 180;
  const r = MAX_RADIUS * fraction;
  return {
    x: CENTER + r * Math.cos(angleRad),
    y: CENTER + r * Math.sin(angleRad),
  };
}

function approxPercentile(
  value: number | null,
  baseline: { p10: number; p90: number } | undefined,
): number | null {
  if (value == null || !baseline) return null;
  const { p10, p90 } = baseline;
  const t = (value - p10) / (p90 - p10);
  return Math.round(Math.max(0, Math.min(1, t)) * 100);
}

function shapePoints<T>(subject: T, stats: readonly RadarStatRef<T>[]): string {
  return stats
    .map((s, i) => {
      const v = s.pick(subject);
      const pct = approxPercentile(v, s.percentileBaseline);
      const f = pct != null ? pct / 100 : 0;
      const { x, y } = vertex(i, Math.max(0.04, f), stats.length);
      return `${x},${y}`;
    })
    .join(' ');
}

export function HexagonalRadar<T>({ stats, a, b, aName, bName }: HexagonalRadarProps<T>) {
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);
  const aPath = shapePoints(a, stats);
  const bPath = shapePoints(b, stats);

  return (
    <div className="flex flex-col items-center gap-5 rounded-l border border-hairline-gold bg-surface-elevated p-6 shadow-md">
      <div className="flex flex-wrap items-center justify-center gap-6 text-[12.5px]">
        <div className="flex items-center gap-2">
          <span className="inline-block h-3 w-3 rounded-sm bg-accent-leather" />
          <span className="text-paper-ink">{aName}</span>
        </div>
        <div className="flex items-center gap-2">
          <span
            className="inline-block h-3 w-3 rounded-sm"
            style={{ backgroundColor: 'var(--accent-gold-light)' }}
          />
          <span className="text-paper-ink">{bName}</span>
        </div>
      </div>

      <svg
        width="100%"
        height="auto"
        viewBox={`0 0 ${SIZE} ${SIZE}`}
        preserveAspectRatio="xMidYMid meet"
        style={{ maxWidth: SIZE }}
        className="block"
        role="img"
        aria-label={`Hexagonal radar comparison of ${aName} vs ${bName}`}
      >
        {/* Concentric guide hexagons at 25/50/75/100 % */}
        {[0.25, 0.5, 0.75, 1].map((frac) => (
          <polygon
            key={frac}
            points={stats
              .map((_, i) => {
                const { x, y } = vertex(i, frac, stats.length);
                return `${x},${y}`;
              })
              .join(' ')}
            fill="none"
            stroke="var(--hairline)"
            strokeWidth={1}
          />
        ))}

        {/* Axis spokes */}
        {stats.map((_, i) => {
          const tip = vertex(i, 1, stats.length);
          return (
            <line
              key={i}
              x1={CENTER}
              y1={CENTER}
              x2={tip.x}
              y2={tip.y}
              stroke="var(--hairline)"
              strokeWidth={1}
            />
          );
        })}

        {/* Subject A — leather */}
        <polygon
          points={aPath}
          fill="rgba(139, 90, 43, 0.50)"
          stroke="var(--accent-leather)"
          strokeWidth={2}
          strokeLinejoin="round"
          style={{ animation: `fadein 400ms cubic-bezier(0.2, 0.8, 0.2, 1) 60ms both` }}
        />
        {/* Subject B — gold-light (original brightness for chroma against cream) */}
        <polygon
          points={bPath}
          fill="rgba(201, 169, 97, 0.50)"
          stroke="var(--accent-gold-light)"
          strokeWidth={2}
          strokeLinejoin="round"
          style={{ animation: `fadein 400ms cubic-bezier(0.2, 0.8, 0.2, 1) 120ms both` }}
        />

        {/* Axis hit-targets + labels */}
        {stats.map((s, i) => {
          const labelTip = vertex(i, 1.18, stats.length);
          const dotTip = vertex(i, 1, stats.length);
          const isHover = hoverIdx === i;
          return (
            <g
              key={s.token}
              onMouseEnter={() => setHoverIdx(i)}
              onMouseLeave={() => setHoverIdx(null)}
              style={{ cursor: 'crosshair' }}
            >
              <circle
                cx={dotTip.x}
                cy={dotTip.y}
                r={isHover ? 6 : 4}
                fill={isHover ? 'var(--accent-leather)' : 'var(--paper-ink-soft)'}
                style={{ transition: 'r 200ms ease-out, fill 200ms ease-out' }}
              />
              <text
                x={labelTip.x}
                y={labelTip.y}
                textAnchor="middle"
                dominantBaseline="middle"
                fill="var(--paper-ink)"
                fontSize={11}
                fontWeight={700}
                letterSpacing="0.04em"
              >
                {s.label}
              </text>
            </g>
          );
        })}
      </svg>

      {/* Caption strip — text-only, lives below the chart so hit-targeting
          doesn't depend on screen-coordinate positioning. */}
      <div className="min-h-[42px] w-full rounded-m border border-hairline bg-surface-sunken px-4 py-2 text-center">
        {hoverIdx != null ? (
          <RadarHoverDetail
            stat={stats[hoverIdx]}
            a={a}
            b={b}
            aName={aName}
            bName={bName}
          />
        ) : (
          <span className="text-[11.5px] italic text-paper-ink-soft">
            Hover any axis dot for both subjects' values
          </span>
        )}
      </div>
    </div>
  );
}

function RadarHoverDetail<T>({
  stat,
  a,
  b,
  aName,
  bName,
}: {
  stat: RadarStatRef<T>;
  a: T;
  b: T;
  aName: string;
  bName: string;
}) {
  const aVal = stat.pick(a);
  const bVal = stat.pick(b);
  return (
    <div className="flex flex-wrap items-baseline justify-center gap-x-5 gap-y-1 text-[12px]">
      <span className="kicker text-paper-ink">{stat.label}</span>
      <span className="text-paper-ink-muted">
        {aName}:{' '}
        <span className="mono font-bold text-accent-leather">{stat.format(aVal)}</span>
      </span>
      <span className="text-paper-ink-muted">
        {bName}:{' '}
        <span
          className="mono font-bold"
          style={{ color: 'var(--accent-gold)' }}
        >
          {stat.format(bVal)}
        </span>
      </span>
    </div>
  );
}
