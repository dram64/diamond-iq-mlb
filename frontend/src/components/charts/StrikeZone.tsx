import type { BatterSide, Pitch, PitchResult } from '@/types';

interface StrikeZoneProps {
  pitches: readonly Pitch[];
  width?: number;
  height?: number;
  batter?: BatterSide;
}

// Plate-coordinate box for the drawn strike zone (inside the SVG canvas).
const ZL = 50;
const ZR = 150;
const ZT = 70;
const ZB = 190;

function colorForResult(result: PitchResult): string {
  switch (result) {
    case 'strike':
    case 'called-strike':
      return '#0b3d8f'; // accent-glow
    case 'hit':
      return '#d50032'; // live
    case 'ball':
      return '#6b7280'; // paper-4
    case 'foul':
    case 'out':
    default:
      return '#4b5563'; // paper-3
  }
}

/** SVG strike zone with pitch locations overlaid. x ∈ [-1,1], y ∈ [0,1]; y > 1 is above the zone. */
export function StrikeZone({
  pitches,
  width = 200,
  height = 240,
  batter = 'R',
}: StrikeZoneProps) {
  const toX = (x: number) => ZL + ((x + 1) * (ZR - ZL)) / 2;
  const toY = (y: number) => ZB - y * (ZB - ZT);

  const batterLabel = batter === 'L' ? 'LHB' : 'RHB';
  const batterX = batter === 'L' ? 22 : width - 22;
  const batterAnchor = batter === 'L' ? 'start' : 'end';

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className="block"
      aria-label="Strike zone · catcher view"
    >
      {/* outer context — outside-zone shading */}
      <rect
        x="16"
        y="36"
        width={width - 32}
        height={height - 72}
        fill="#f9fafb"
        opacity="0.4"
        rx="4"
      />

      {/* LHB / RHB label */}
      <text
        x={batterX}
        y={height / 2 + 4}
        fontFamily="var(--font-mono, 'JetBrains Mono')"
        fontSize="9"
        fill="#9ca3af"
        textAnchor={batterAnchor}
      >
        {batterLabel}
      </text>

      {/* strike-zone box */}
      <rect
        x={ZL}
        y={ZT}
        width={ZR - ZL}
        height={ZB - ZT}
        fill="none"
        stroke="#4b5563"
        strokeWidth="1"
      />

      {/* vertical thirds */}
      <line x1={ZL + (ZR - ZL) / 3} x2={ZL + (ZR - ZL) / 3} y1={ZT} y2={ZB}
            stroke="#f3f4f6" strokeDasharray="2 3" />
      <line x1={ZL + (2 * (ZR - ZL)) / 3} x2={ZL + (2 * (ZR - ZL)) / 3} y1={ZT} y2={ZB}
            stroke="#f3f4f6" strokeDasharray="2 3" />
      {/* horizontal thirds */}
      <line x1={ZL} x2={ZR} y1={ZT + (ZB - ZT) / 3} y2={ZT + (ZB - ZT) / 3}
            stroke="#f3f4f6" strokeDasharray="2 3" />
      <line x1={ZL} x2={ZR} y1={ZT + (2 * (ZB - ZT)) / 3} y2={ZT + (2 * (ZB - ZT)) / 3}
            stroke="#f3f4f6" strokeDasharray="2 3" />

      {/* home plate outline */}
      <path
        d={`M ${ZL} ${ZB + 20} L ${ZR} ${ZB + 20} L ${ZR - 10} ${ZB + 32} L ${(ZL + ZR) / 2} ${ZB + 40} L ${ZL + 10} ${ZB + 32} Z`}
        fill="none"
        stroke="#9ca3af"
        strokeWidth="1"
      />

      {/* pitch markers */}
      {pitches.map((p) => {
        const cx = toX(p.x);
        const cy = toY(p.y);
        const color = colorForResult(p.result);
        return (
          <g key={p.n}>
            <circle cx={cx} cy={cy} r="9" fill={color} opacity="0.18" />
            <circle
              cx={cx}
              cy={cy}
              r="6"
              fill={color}
              stroke="#ffffff"
              strokeWidth="1"
            />
            <text
              x={cx}
              y={cy + 3}
              fontFamily="var(--font-mono, 'JetBrains Mono')"
              fontSize="8"
              fontWeight="600"
              fill="#0a0a0a"
              textAnchor="middle"
            >
              {p.n}
            </text>
          </g>
        );
      })}

      {/* axis title */}
      <text
        x="16"
        y="28"
        fontFamily="Inter"
        fontSize="9"
        letterSpacing="0.1em"
        fill="#9ca3af"
      >
        STRIKE ZONE · CATCHER VIEW
      </text>
    </svg>
  );
}
