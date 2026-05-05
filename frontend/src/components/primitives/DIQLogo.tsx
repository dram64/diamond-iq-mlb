interface DIQLogoProps {
  size?: number;
  mono?: boolean;
}

/** Diamond IQ wordmark with geometric glyph. `mono` uses currentColor for use on dark surfaces. */
export function DIQLogo({ size = 22, mono = false }: DIQLogoProps) {
  const ink = mono ? 'currentColor' : 'var(--diq-accent, #002d72)';
  const paper = mono ? 'currentColor' : 'var(--diq-paper, #0a0a0a)';
  return (
    <span className="inline-flex items-center gap-[9px] leading-none">
      <svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        style={{ display: 'block' }}
        aria-hidden="true"
      >
        <path d="M12 1.5 L22.5 12 L12 22.5 L1.5 12 Z" fill={ink} stroke={ink} strokeWidth="1" />
        <path d="M12 6 L18 12 L12 18 L6 12 Z" fill="#ffffff" />
        <circle cx="12" cy="12" r="1.5" fill={ink} />
      </svg>
      <span
        className="font-sans font-extrabold tracking-tight"
        style={{ fontSize: size * 0.82, color: paper }}
      >
        Diamond<span style={{ color: ink }}> IQ</span>
      </span>
    </span>
  );
}
