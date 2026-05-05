interface PlayerSilhouetteProps {
  size?: number;
}

/** Neutral circular avatar placeholder for players without a headshot. */
export function PlayerSilhouette({ size = 40 }: PlayerSilhouetteProps) {
  return (
    <span
      className="flex shrink-0 items-end justify-center overflow-hidden rounded-full border border-hairline-strong bg-surface-2"
      style={{ width: size, height: size }}
      aria-hidden="true"
    >
      <svg
        width={size * 0.62}
        height={size * 0.62}
        viewBox="0 0 24 24"
        fill="#9ca3af"
      >
        <circle cx="12" cy="9" r="4" />
        <path d="M4 22 C 4 16, 20 16, 20 22 Z" />
      </svg>
    </span>
  );
}
