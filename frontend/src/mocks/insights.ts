import type { AIInsight, ComparePreviewSide, FeaturedStat } from '@/types';

export const AI_INSIGHTS: readonly AIInsight[] = [
  {
    topic: 'Arroyo keeps hitting the fastball',
    blurb:
      "Sierra's Marco Arroyo is 7-for-12 vs 97+ mph fastballs over the last week. Volkov has thrown 42 four-seamers tonight.",
    tag: 'STR · KNG',
  },
  {
    topic: "Caruana's nine-inning complete-game chase",
    blurb:
      "Shoreline's ace is through 3 innings on 38 pitches. On pace for a 97-pitch CG — would be the league's first since 2023.",
    tag: 'SHL · RVR',
  },
  {
    topic: "Foxes' bullpen is cooked",
    blurb:
      "Kingsport's relievers have thrown 19 innings in the last 4 days. Leverage arms likely unavailable tonight.",
    tag: 'Trend',
  },
];

export const FEATURED_STATS: readonly FeaturedStat[] = [
  { label: 'Win probability', value: '64%',  sub: 'Sierra',                  accent: true },
  { label: 'Leverage index',  value: '3.42', sub: 'High leverage' },
  { label: 'Pitches thrown',  value: '92',   sub: 'Volkov · season hi 104' },
  { label: 'Expected runs',   value: '1.47', sub: 'This inning' },
];

export interface ComparePreview {
  a: ComparePreviewSide;
  b: ComparePreviewSide;
}

export const COMPARE_PREVIEW: ComparePreview = {
  a: {
    name: 'M. Arroyo',
    team: 'STR',
    pos: 'CF',
    stats: { AVG: 0.341, HR: 38, RBI: 102, WAR: 8.2, 'OPS+': 178 },
  },
  b: {
    name: 'E. Caruana',
    team: 'SHL',
    pos: 'RF',
    stats: { AVG: 0.302, HR: 29, RBI: 94, WAR: 7.8, 'OPS+': 162 },
  },
};

/** Max axis values for normalizing the compare-strip bars. */
export const COMPARE_MAX: Readonly<Record<string, number>> = {
  AVG: 0.4,
  HR: 50,
  RBI: 130,
  WAR: 10,
  'OPS+': 200,
};
