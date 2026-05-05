import { describe, expect, it } from 'vitest';

import { FEATURED_COMPARISONS, getFeaturedComparison } from './featuredComparisons';

describe('FEATURED_COMPARISONS', () => {
  it('every matchup pairs exactly two distinct MLB person IDs', () => {
    for (const m of FEATURED_COMPARISONS) {
      expect(m.playerIds).toHaveLength(2);
      expect(m.playerIds[0]).not.toBe(m.playerIds[1]);
      expect(typeof m.playerIds[0]).toBe('number');
      expect(typeof m.playerIds[1]).toBe('number');
    }
  });

  it('ids and titles are unique across the list', () => {
    const ids = FEATURED_COMPARISONS.map((m) => m.id);
    const titles = FEATURED_COMPARISONS.map((m) => m.title);
    expect(new Set(ids).size).toBe(ids.length);
    expect(new Set(titles).size).toBe(titles.length);
  });
});

describe('getFeaturedComparison', () => {
  it('returns the matching entry for a known id', () => {
    expect(getFeaturedComparison('judge-alvarez')?.title).toBe('Judge vs Alvarez');
  });

  it('returns undefined for an unknown id', () => {
    expect(getFeaturedComparison('not-a-real-id')).toBeUndefined();
  });
});
