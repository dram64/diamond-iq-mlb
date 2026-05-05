/**
 * Team chip — renders the team's cap-logo SVG over the club's primary color
 * with the abbreviation as a fallback when the logo is missing or fails to
 * load. Purely presentational; the caller resolves the visual data.
 */

import { useState } from 'react';

const FALLBACK_COLOR = '#27272a';

interface TeamChipProps {
  abbr: string;
  /** Hex color (with leading #) or empty string. Empty falls back to dark gray. */
  color: string;
  /** Public-relative path to the team's logo SVG. Empty/undefined skips the logo. */
  logoPath?: string;
  size?: number;
}

export function TeamChip({ abbr, color, logoPath, size = 28 }: TeamChipProps) {
  const c = color || FALLBACK_COLOR;
  const [logoBroken, setLogoBroken] = useState(false);
  const showLogo = !!logoPath && !logoBroken;

  return (
    <span
      className="inline-flex shrink-0 items-center justify-center font-sans font-extrabold text-white"
      style={{
        width: size,
        height: size,
        borderRadius: 4,
        background: `linear-gradient(180deg, ${c}, ${c}cc)`,
        fontSize: size * 0.38,
        letterSpacing: '0.02em',
        boxShadow: 'inset 0 0 0 1px rgba(0,0,0,0.08)',
      }}
      aria-label={abbr}
    >
      {showLogo ? (
        <img
          src={logoPath}
          alt=""
          className="block"
          style={{ width: size * 0.78, height: size * 0.78, objectFit: 'contain' }}
          onError={() => setLogoBroken(true)}
        />
      ) : (
        abbr
      )}
    </span>
  );
}
