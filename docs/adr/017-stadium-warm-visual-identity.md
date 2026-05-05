# ADR 017 — Stadium-warm visual identity

## Status

Accepted (Phase 8 — April 2026, foundation only). Phase 8.5 will roll
the chosen stat-display treatment from `/design-preview` across all
comparison surfaces and remove the losing three.

This is a real **design** ADR, not a feature ADR. Where ADR 015 / 016
captured product capabilities, this one captures the visual system that
those capabilities are presented in.

## Context

Through Phase 7 the dashboard rendered on a clean white-on-gray surface
with an accent-blue `#002d72` (literal MLB navy). Functional, but
generic — the project had grown past "competent dashboard" into a
domain-rich product (live games, AI recaps, Statcast, awards), and the
neutral palette undersold the personality.

User wanted a single coherent visual direction that:

  - Reads as "baseball" without leaning on team logos as crutches
  - Carries warmth (we are a fan product, not a Bloomberg terminal)
  - Holds together at both editorial scale (home page hero, featured
    matchup) and dashboard density (compare, stats explorer)
  - Works in a single deploy without breaking existing layouts

The brief named the direction "Stadium-warm." This ADR captures the
specific decisions.

## Decisions

### 1. Palette grounded in stadium photography

Reference set:

  - Wrigley night-game photographs for the navy/cream balance
  - Macro photographs of broken-in glove leather for the leather/gold pair
  - Vintage wool-flannel uniforms for the cream tonality

Hex values, finalized after Gate 1 surfacing:

| Role | Hex | Notes |
|---|---|---|
| Surface base | `#0E1F38` | Page background — deep navy with a slight green undertone, reads as "stadium under lights" rather than "tech UI dark mode" |
| Surface elevated | `#152A4A` | Cards, hovered surfaces |
| Surface elevated-hover | `#1B355C` | Card hover state |
| Surface sunken | `#0A1830` | Footer, inset wells, search-input field |
| Paper cream | `#F4EAD5` | Primary text — warm white biased toward yellow, like vintage flannel |
| Paper cream-2 | `#E8DCC2` | Slightly muted cream for secondary heads |
| Paper gray | `#A8B4C8` | Cool gray for kickers, axis labels |
| Paper gray-dim | `#6E7E96` | Footer copy, disabled controls |
| Accent leather | `#8B5A2B` | Primary accent — broken-in glove leather. Active states, links, primary CTAs |
| Accent leather-glow | `#A8723A` | Hover lift of leather |
| Accent gold | `#C9A961` | Secondary accent / data emphasis. Big numbers, "winner" emphasis on bars + rings + cards |
| Accent gold-soft | `#A88B4D` | Muted gold for borders + backgrounds |
| Hairline | `rgba(244, 234, 213, 0.08)` | Default border — cream at 8 % opacity |
| Hairline strong | `rgba(244, 234, 213, 0.16)` | Section dividers |
| Hairline gold | `rgba(201, 169, 97, 0.18)` | Default Card outline — picks up the gold accent without being assertive |
| Good | `#5DA876` | Positive deltas, final-score winner |
| Bad | `#C76456` | Errors, negative deltas — warm coral, not stoplight red |
| Live | `#E27649` | Live-pulse dot — warm orange, reads as urgent against the cool navy |

Every value passes WCAG AA contrast against `#0E1F38`. Cream-on-navy
clears AAA for body text.

### 2. CSS variables as the source of truth

All hex values live in `:root` declarations in `src/index.css`. Tailwind
utilities (`text-paper-cream`, `bg-surface-elevated`) resolve through
`var(--paper-cream)` etc., so:

  - Non-Tailwind code (SVG fills, inline styles, animations) reads from
    the same source via `fill="var(--accent-gold)"`
  - Future palette refinements happen in one file
  - Per-page theme overrides (Phase 8.5+) can scope `:root` in a
    `.theme-x` class without forking utilities

### 3. Backwards-compatible token aliases

The Phase 5G-era token names (`surface.0..3`, `paper.DEFAULT/2..5`,
`accent.DEFAULT/soft/glow`, `hairline`, `good`, `bad`, `live`) are
preserved as **aliases** in the Tailwind config, mapped onto the new
Stadium-warm equivalents. Existing components keep rendering through
the Phase 8 / 8.5 transition window without code changes.

This lets us ship the foundation in one deploy without cascading
breakage. Visual transitional weirdness (a card authored against a
white background showing cream-on-navy) is the expected trade. Phase
8.5 will retire those alias names as it refits each page surface.

### 4. Typography — Inter 800 + JetBrains Mono, no new dependencies

The brief allowed an editorial serif (Tiempos / Söhne / Georgia
fallbacks). Considered and rejected:

  - **Pro of a serif:** more authentically editorial, picks up the
    "feature story" voice of a baseball longread
  - **Con:** +60-100 KB self-hosted woffs (we already self-host Inter +
    JetBrains Mono per Phase 5J). Visual incoherence with the existing
    JetBrains-Mono numerals across all stat surfaces.

Decision: Inter 800 with `-0.02em` letter-spacing on the new `.display`
utility class — produces a tight, scoreboard-digit feel that pairs
cleanly with JetBrains-Mono `tabular-nums` for stat values. Zero new
font-loading cost.

If a future need surfaces a real headline serif, swap is one tailwind
config edit + one `@fontsource/tiempos` install. Phase 8 doesn't pay
that cost.

### 5. Type scale

```
Display       72px / 1.0  / 800 / -0.02em   hero numbers (Featured Matchup)
Display-2     48px / 1.05 / 800 / -0.02em   page-title h1 (rare)
H1            36px / 1.1  / 700 / -0.015em  /compare-players, /design-preview
H2            24px / 1.2  / 700 / -0.01em   section heads
H3            18px / 1.3  / 700 / -0.005em
Body-lg       16px / 1.55 / 400             long-form copy (recap, AI commentary)
Body          14px / 1.5  / 400             default UI body
Body-sm       13px / 1.45 / 400             tables, secondary
Caption       12px / 1.45 / 400             footnotes, axis labels
Kicker      10.5px / 1.0  / 700 / 0.08em    "TODAY'S FEATURED MATCHUP" labels
```

Numeric face: JetBrains Mono `font-variant-numeric: tabular-nums` —
applied through the existing `.mono` and the new `.display` utilities.

### 6. Spacing — page-personality classes

Two density modes baked into `index.css`:

  - **`.page-editorial`** — outer `36px 28px 64px` padding, `40px`
    between sections. Use on `Home`, hero-led surfaces. Generous
    whitespace, larger hero numbers, full-saturation gold accents.
  - **`.page-data`** — outer `24px 20px 48px`, `20px` between
    sections. Use on `/compare-players`, `/teams`, `/stats`,
    `/teams/:id`, `/design-preview`. Tighter grid spacing, smaller
    type, gold reserved for winners + active states.

Phase 8 only applies `.page-data` to `/design-preview`. Phase 8.5 will
retro-fit the existing page surfaces.

### 7. Texture — SVG noise grain at 4 %

`body::before` carries an inline SVG `<filter feTurbulence>` data URL
(~600 bytes) tinted toward warm cream and stamped at 4 % opacity over
the entire viewport.

Why: a flat dark surface reads as "tech UI dark mode" — not what we
want. Subtle grain texture adds the depth that real-world stadium
photography has. 4 % opacity keeps it under the threshold of
"distracting" while staying perceptible to a designer's eye.

Position: `fixed`, `pointer-events: none`, `z-index: 0`. Sits beneath
all content but above the body background. The app shell stacks at
`z-index: 1` so the grain never leaks into focus rings or shadows.

### 8. Animation — 200 ms ease-out, no bouncing

All hover transitions: `200ms cubic-bezier(0.2, 0.8, 0.2, 1)` (a soft
ease-out curve — fast start, gentle land).

  - Cards: `transition-colors duration-200 ease-out` on hover
  - Stat values: `fadein` keyframe on initial render with
    50-100 ms stagger via inline `animation-delay`
  - Percentile rings: `stroke-dashoffset` transition at 400 ms
  - Diverging bars: `bargrow` keyframe (scaleX from 0 → 1) at 400 ms
    with origin set to the bar's anchor end

No spring physics, no pop, no slide-from-edge. The quietest possible
motion that still says "this is a live, responsive interface."

### 9. Card primitive — gold-tinted hairline, ambient lift

`<Card>` renders with:

  - `border: 1px solid var(--hairline-gold)` (rgba 201,169,97,0.18 —
    just enough warmth to say "this card lives in a stadium-warm
    universe" without a visible gold edge)
  - `box-shadow: inset 0 1px 0 rgba(244,234,213,0.04), 0 4px 14px rgba(0,0,0,0.32)`
    (cream rim-light on top simulating a stadium fixture, dark
    drop-shadow below for ambient lift)
  - `transition-colors duration-200 ease-out` for hover

The hover state — `shadow-gold` — adds an outer gold ambient glow
`0 6px 20px rgba(201,169,97,0.10)` for any card-as-link surface (Stat
Battles winner cards, search-result rows, team-grid tiles).

### 10. Percentile-fallback strategy in `/design-preview` Treatment 1

Treatment 1 (Percentile Rings) needs percentile rank data. We don't
have a server-side percentile API yet. Phase 8 ships a **placeholder
linear approximation** from hand-tuned (p10, p90) baselines per stat
(e.g. `avg_hit_speed: { p10: 86, p90: 95 }`):

```ts
function approxPercentile(value, ref) {
  const { p10, p90 } = ref.percentileBaseline;
  const t = (value - p10) / (p90 - p10);
  return Math.round(Math.max(0, Math.min(1, t)) * 100);
}
```

This **is not a real MLB percentile**. It produces correct-looking
hero-stat reads (Aaron Judge's 94.7 mph EV → ~96th, Ohtani's 95.5 →
~100th) but mis-handles the long tail. Treatment 1's UI carries an
explicit footnote: *"Percentiles approximated from current-season
qualified pool — server-computed rank lands in Phase 8.5."*

Phase 8.5 will swap in real server-computed rank if the user picks
Treatment 1. The frontend hook will stay the same; the
`approxPercentile` math gets replaced by a per-stat read from a new
API field.

### 11. The four design-preview treatments

Each treatment renders the same `useCompare([592450, 660271])` data
(Aaron Judge vs Shohei Ohtani — chosen because Ohtani is two-way and
exposes asymmetric-data handling). Each treatment handles two-way
players differently — by design, so the tradeoffs are visible:

  - **Treatment 1 — Percentile rings.** 8-stat hitter-only grid. Two
    SVG gauges per stat. Ohtani's pitcher metrics not shown here.
  - **Treatment 2 — Diverging bars.** Filters to stats where BOTH
    players have values — Ohtani's pitcher metrics drop out for a
    Judge pairing. Best for symmetric matchups.
  - **Treatment 3 — Stat battles (card grid).** Renders all hitter +
    pitcher cards. When one player has no data on the comparison
    side, that side shows a "no comparison" italic hint, keeping
    grid alignment.
  - **Treatment 4 — Hexagonal radar.** 6-axis hitter-only radar
    overlaying both players' shapes. Pitcher metrics excluded —
    different stat scales would make a unified hex meaningless.

### 12. What stays out of Phase 8 (deferred to 8.5+)

  - Refit of the home page hero / Featured Matchup card to the new
    palette (currently looks transitionally weird — leather-tinted
    league badges where they used to be accent-blue)
  - Roll-out of the chosen treatment across `/compare-players`,
    `/compare-teams`, `/teams/:id`
  - Removal of legacy alias names from the Tailwind config
  - Real server-computed percentile API (only ships if Treatment 1
    wins the user's pick)
  - AI placeholder cleanup — separate cleanup phase

## Consequences

### Positive

  - **Single coherent visual direction.** Stadium-warm reads as
    "baseball product" without leaning on team logos as crutches.
  - **Backwards-compatible.** Legacy token aliases let the foundation
    ship in one deploy without cascading layout breakage.
  - **Zero new dependencies.** No font additions, no design library,
    no icon pack. Cost: ~2.2 KB CSS gzip + 0 KB JS for the foundation
    (plus ~5 KB gzip for the design-preview chunk that won't ship to
    end users).
  - **CSS-vars-as-source-of-truth** lets non-Tailwind surfaces (SVG
    fills, inline styles, future per-page theme overrides) read from
    the same palette.
  - **Decision path for stat-display treatment.** `/design-preview`
    lets the user evaluate four candidates side-by-side against
    real Judge-vs-Ohtani data, pick one, then Phase 8.5 rolls it.

### Negative

  - **Transitional visual weirdness on existing pages.** Home page
    Featured Matchup, /compare-players header chips, /teams card
    accents will all carry leftover Phase 5-7 styling that doesn't
    quite mesh with the new palette until 8.5 retro-fits each
    surface.
  - **Percentile data is approximate** in Treatment 1 — Phase 8.5
    work needed if it wins.
  - **`/design-preview` is direct-URL only** — no navbar entry. A
    new visitor won't find it without being told the URL. This is
    intentional; the page is a private decision sandbox, not a
    user-facing surface.
  - **Legacy alias names** in the Tailwind config are
    architecturally noisy. They earn their keep in Phase 8 by
    avoiding cascading rewrites; Phase 8.5 retires them as it
    refits each page.

## References

  - Wrigley Field night-game photography (visual reference for the
    navy/cream balance)
  - Rawlings Heart of the Hide glove brochures (leather/gold tonal
    pair)
  - Vintage MLB wool-flannel uniform photography (cream tonality)
  - The existing [ADR 012](012-player-data-architecture.md) section
    on player-data domain — none of those decisions changed; this
    ADR sits adjacent to product architecture
  - [ADR 015](015-phase-6-feature-expansion.md) and
    [ADR 016](016-statcast-integration.md) for the prior phases'
    feature-surface decisions that this visual system inherits
