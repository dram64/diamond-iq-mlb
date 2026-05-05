import { useState } from 'react';

export type PlayerHeadshotSize = 'sm' | 'md' | 'lg';

interface PlayerHeadshotProps {
  /** MLB player ID. When missing/null, the component renders the initials
   *  fallback directly without attempting an image fetch. */
  playerId?: number | string | null;
  /** Used as alt text and as the source for initials when the image is
   *  unavailable. */
  playerName?: string | null;
  size?: PlayerHeadshotSize;
  className?: string;
}

const SIZE_CLASS: Record<PlayerHeadshotSize, string> = {
  // Tailwind has both `w-N`/`h-N` utilities AND CSS variables; using
  // arbitrary values keeps the JIT scanner from missing them when used
  // dynamically. Pixel sizes match the spec: sm 32, md 48, lg 96.
  sm: 'w-8 h-8 text-[10px]',
  md: 'w-12 h-12 text-[13px]',
  lg: 'w-24 h-24 text-[24px]',
};

const SIZE_PX: Record<PlayerHeadshotSize, number> = { sm: 32, md: 48, lg: 96 };

function mlbHeadshotUrl(playerId: number | string): string {
  return (
    `https://img.mlbstatic.com/mlb-photos/image/upload/` +
    `d_people:generic:headshot:67:current.png/w_180,q_auto:best/` +
    `v1/people/${playerId}/headshot/67/current`
  );
}

/** Compute a 1-2 character initials string from a player's name.
 *  - "Aaron Judge"  → "AJ"
 *  - "Pedro"        → "P"
 *  - "Jr." / "III"  → ignored as last-name candidates
 *  - missing / empty / whitespace → "" (caller renders blank circle) */
// eslint-disable-next-line react-refresh/only-export-components
export function initialsOf(name: string | null | undefined): string {
  if (!name) return '';
  const trimmed = name.trim();
  if (!trimmed) return '';
  // Filter out the bits no one means as a name (suffixes, single letters).
  const SUFFIX = /^(jr\.?|sr\.?|i{1,3}|iv|v)$/i;
  const parts = trimmed.split(/\s+/).filter((p) => !SUFFIX.test(p));
  if (parts.length === 0) return '';
  if (parts.length === 1) return parts[0][0]!.toUpperCase();
  const first = parts[0][0] ?? '';
  const last = parts[parts.length - 1][0] ?? '';
  return (first + last).toUpperCase();
}

export function PlayerHeadshot({
  playerId,
  playerName,
  size = 'md',
  className = '',
}: PlayerHeadshotProps) {
  const [errored, setErrored] = useState(false);

  const initials = initialsOf(playerName);
  const sizeClass = SIZE_CLASS[size];
  const px = SIZE_PX[size];

  const showFallback =
    playerId === undefined || playerId === null || playerId === '' || errored;

  if (showFallback) {
    return (
      <span
        className={[
          'inline-flex shrink-0 items-center justify-center rounded-full bg-surface-3 font-semibold text-paper-3',
          sizeClass,
          className,
        ].join(' ')}
        role="img"
        aria-label={playerName ?? 'Unknown player'}
      >
        {initials}
      </span>
    );
  }

  return (
    <img
      src={mlbHeadshotUrl(playerId)}
      alt={playerName ?? ''}
      width={px}
      height={px}
      loading="lazy"
      decoding="async"
      onError={() => setErrored(true)}
      className={[
        'shrink-0 rounded-full bg-surface-3 object-cover',
        sizeClass,
        className,
      ].join(' ')}
    />
  );
}
