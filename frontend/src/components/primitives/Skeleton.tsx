import type { CSSProperties } from 'react';

interface SkeletonProps {
  /** Tailwind utility classes for sizing/shape. */
  className?: string;
  /** Inline style for one-off width/height when classes don't fit. */
  style?: CSSProperties;
}

/** Animated gray placeholder used during initial loading states. */
export function Skeleton({ className = '', style }: SkeletonProps) {
  return (
    <div
      aria-hidden="true"
      className={`animate-pulse rounded-m bg-surface-3 ${className}`}
      style={style}
    />
  );
}
