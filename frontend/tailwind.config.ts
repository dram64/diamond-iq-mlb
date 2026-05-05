import type { Config } from 'tailwindcss';

/**
 * Stadium-warm visual identity (Phase 8.5 — cream-dominant flip).
 *
 * Phase 8 made navy dominant; that obscured logos and hurt readability.
 * Phase 8.5 inverts the ratio: cream is the primary surface (warm
 * paper), navy becomes a structural accent (header bands, hero
 * overlays). Leather brown + muted gold are unchanged in role; the
 * gold is darkened to clear AA against cream (the brighter Phase 8
 * gold lives on as `accent.gold-light` for use inside navy bands).
 *
 * All hex values resolve through CSS variables in src/index.css so
 * non-Tailwind code (SVG fills, inline styles) reads from the same
 * source via var(--paper-ink) etc.
 *
 * Backwards compatibility: the legacy 5G-era token names (surface.0..3,
 * paper.DEFAULT/2..5, accent.DEFAULT/soft/glow, hairline, good, bad,
 * live) are preserved as aliases — but with three CRITICAL FLIPS so
 * existing components keep rendering readably:
 *
 *   - paper.DEFAULT = paper.ink (was paper-cream — flipped to dark text)
 *   - hairline      = ink-at-10% (was cream-at-8%)
 *   - ink           = paper.ink (was paper-cream — flipped to dark text)
 *
 * Without those three, every Phase 5–7 component that reads
 * `text-paper-2` or `border-hairline` would render invisible the moment
 * the palette flipped.
 */
const config: Config = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // ── Stadium-warm cream-dominant palette ────────────────────────
        surface: {
          base: 'var(--surface-base)',
          elevated: 'var(--surface-elevated)',
          'elevated-hover': 'var(--surface-elevated-hover)',
          sunken: 'var(--surface-sunken)',
          // NEW Phase 8.5 — navy structural bands. Use ONLY for header
          // strips, hero overlays, and footer accents — NOT for page
          // backgrounds or default card surfaces.
          navy: 'var(--surface-navy)',
          'navy-deep': 'var(--surface-navy-deep)',
          // Legacy aliases (Phase 5G → 8.5 transition) — flipped so
          // existing components land on cream surfaces.
          0: 'var(--surface-base)',
          1: 'var(--surface-elevated)',
          2: 'var(--surface-sunken)',
          3: 'var(--surface-sunken)',
        },
        paper: {
          // Default text is now ink-on-cream.
          DEFAULT: 'var(--paper-ink)',
          ink: 'var(--paper-ink)',
          'ink-muted': 'var(--paper-ink-muted)',
          'ink-soft': 'var(--paper-ink-soft)',
          // Cream tokens are reserved for text-on-navy (inside
          // surface.navy bands only).
          cream: 'var(--paper-cream)',
          'cream-2': 'var(--paper-cream-2)',
          // Legacy gray ramps — flipped to ink ramp so old code reads.
          gray: 'var(--paper-ink-soft)',
          'gray-dim': 'var(--paper-ink-soft)',
          // Numeric legacy aliases (paper.2 / 3 / 4 / 5).
          2: 'var(--paper-ink)',
          3: 'var(--paper-ink-muted)',
          4: 'var(--paper-ink-soft)',
          5: 'var(--paper-ink-soft)',
        },
        accent: {
          DEFAULT: 'var(--accent-leather)',
          leather: 'var(--accent-leather)',
          'leather-glow': 'var(--accent-leather-glow)',
          // gold is the darkened-for-cream Phase 8.5 hex; gold-light
          // preserves the original Phase 8 brightness for use inside
          // navy structural bands where contrast flips.
          gold: 'var(--accent-gold)',
          'gold-light': 'var(--accent-gold-light)',
          'gold-soft': 'var(--accent-gold-soft)',
          // Legacy aliases.
          soft: 'var(--accent-leather)',
          glow: 'var(--accent-leather-glow)',
          wash: 'rgba(139, 90, 43, 0.10)',
        },
        hairline: {
          DEFAULT: 'var(--hairline)',
          strong: 'var(--hairline-strong)',
          gold: 'var(--hairline-gold)',
        },
        good: 'var(--good)',
        bad: 'var(--bad)',
        live: {
          DEFAULT: 'var(--live)',
          soft: 'rgba(200, 79, 31, 0.08)',
        },
        ink: 'var(--paper-ink)', // legacy alias — was cream, now ink
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', '-apple-system', 'BlinkMacSystemFont', 'sans-serif'],
        display: ['Inter', 'ui-sans-serif', '-apple-system', 'sans-serif'],
        serif: ['Inter', 'ui-sans-serif', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'SF Mono', 'Menlo', 'monospace'],
      },
      fontSize: {
        display: ['72px', { lineHeight: '1', letterSpacing: '-0.02em', fontWeight: '800' }],
        'display-2': ['48px', { lineHeight: '1.05', letterSpacing: '-0.02em', fontWeight: '800' }],
        h1: ['36px', { lineHeight: '1.1', letterSpacing: '-0.015em', fontWeight: '700' }],
        h2: ['24px', { lineHeight: '1.2', letterSpacing: '-0.01em', fontWeight: '700' }],
        h3: ['18px', { lineHeight: '1.3', letterSpacing: '-0.005em', fontWeight: '700' }],
        'body-lg': ['16px', { lineHeight: '1.55' }],
        body: ['14px', { lineHeight: '1.5' }],
        'body-sm': ['13px', { lineHeight: '1.45' }],
        caption: ['12px', { lineHeight: '1.45' }],
        kicker: ['10.5px', { lineHeight: '1', letterSpacing: '0.08em', fontWeight: '700' }],
      },
      borderRadius: {
        s: '4px',
        m: '6px',
        l: '10px',
      },
      boxShadow: {
        // Subtle paper-on-paper lift — softer than Phase 8's stadium-light
        // ambient since shadows on cream need less depth to read.
        sm: '0 1px 2px rgba(26, 40, 66, 0.06)',
        md: '0 2px 8px rgba(26, 40, 66, 0.08), 0 1px 2px rgba(26, 40, 66, 0.04)',
        lg: '0 8px 24px rgba(26, 40, 66, 0.10), 0 2px 4px rgba(26, 40, 66, 0.05)',
        // Gold-tint shadow for hovered cards (replaces Phase 8's gold
        // ambient glow with a slightly warmer tone-on-cream).
        gold: '0 6px 20px rgba(184, 150, 77, 0.16), 0 1px 2px rgba(26, 40, 66, 0.04)',
      },
      keyframes: {
        livepulse: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.35' },
        },
        fadein: {
          from: { opacity: '0', transform: 'translateY(4px)' },
          to: { opacity: '1', transform: 'none' },
        },
        ringfill: {
          from: { strokeDashoffset: 'var(--ring-circumference, 314)' },
          to: { strokeDashoffset: 'var(--ring-fill-target, 0)' },
        },
        bargrow: {
          from: { transform: 'scaleX(0)' },
          to: { transform: 'scaleX(1)' },
        },
      },
      animation: {
        livepulse: 'livepulse 1.8s ease-in-out infinite',
        fadein: 'fadein 0.2s cubic-bezier(0.2, 0.8, 0.2, 1) both',
        ringfill: 'ringfill 0.4s cubic-bezier(0.2, 0.8, 0.2, 1) both',
        bargrow: 'bargrow 0.4s cubic-bezier(0.2, 0.8, 0.2, 1) both',
      },
      maxWidth: {
        page: '1360px',
      },
      letterSpacing: {
        kicker: '0.08em',
        tighter: '-0.02em',
      },
      transitionTimingFunction: {
        out: 'cubic-bezier(0.2, 0.8, 0.2, 1)',
      },
    },
  },
  plugins: [],
};

export default config;
