interface SparklineProps {
  data: readonly number[];
  width?: number;
  height?: number;
  stroke?: string;
  fill?: string;
  showEnd?: boolean;
}

/** Lightweight SVG sparkline. Min/max auto-fit; area-fill optional. */
export function Sparkline({
  data,
  width = 120,
  height = 28,
  stroke = '#4b5563',
  fill = 'none',
  showEnd = true,
}: SparklineProps) {
  if (data.length < 2) return null;

  const max = Math.max(...data);
  const min = Math.min(...data);
  const span = Math.max(0.001, max - min);
  const stepX = width / (data.length - 1);

  const pts = data.map<[number, number]>((v, i) => [
    i * stepX,
    height - ((v - min) / span) * (height - 4) - 2,
  ]);

  const path = pts
    .map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)} ${y.toFixed(1)}`)
    .join(' ');
  const area = `${path} L ${width} ${height} L 0 ${height} Z`;

  const lastIdx = pts.length - 1;
  const last = pts[lastIdx];

  return (
    <svg width={width} height={height} className="block" aria-hidden="true">
      {fill !== 'none' && <path d={area} fill={fill} opacity="0.35" />}
      <path
        d={path}
        fill="none"
        stroke={stroke}
        strokeWidth="1.25"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {showEnd && last && (
        <circle cx={last[0]} cy={last[1]} r="2" fill={stroke} />
      )}
    </svg>
  );
}
