import type { Bases } from '@/types';

interface BaseDiamondProps {
  bases?: Bases;
  size?: number;
}

const EMPTY: Bases = { first: false, second: false, third: false };

/** Inline SVG of the four bases; filled bases show in accent color. */
export function BaseDiamond({ bases, size = 44 }: BaseDiamondProps) {
  const b = bases ?? EMPTY;
  const on = '#002d72';
  const off = '#d1d5db';
  return (
    <svg
      width={size}
      height={size * 0.9}
      viewBox="0 0 44 40"
      className="block"
      aria-hidden="true"
    >
      {/* 2nd */}
      <rect x="18" y="2"  width="8" height="8" transform="rotate(45 22 6)"
            fill={b.second ? on : 'transparent'} stroke={b.second ? on : off} strokeWidth="1.25" />
      {/* 3rd */}
      <rect x="4"  y="16" width="8" height="8" transform="rotate(45 8 20)"
            fill={b.third ? on : 'transparent'} stroke={b.third ? on : off} strokeWidth="1.25" />
      {/* 1st */}
      <rect x="32" y="16" width="8" height="8" transform="rotate(45 36 20)"
            fill={b.first ? on : 'transparent'} stroke={b.first ? on : off} strokeWidth="1.25" />
      {/* home */}
      <rect x="18" y="30" width="8" height="8" transform="rotate(45 22 34)"
            fill="#ffffff" stroke="#6b7280" strokeWidth="1.25" />
    </svg>
  );
}
