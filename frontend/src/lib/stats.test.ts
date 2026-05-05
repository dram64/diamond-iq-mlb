import { describe, expect, it } from 'vitest';

import { compareStatBetter, formatStat, isAscendingStat } from './stats';

describe('formatStat', () => {
  it('passes through API-formatted strings unchanged', () => {
    expect(formatStat('avg', '.300')).toBe('.300');
    expect(formatStat('era', '3.50')).toBe('3.50');
  });

  it('formats woba to 3 decimals with leading zero stripped', () => {
    expect(formatStat('woba', 0.399)).toBe('.399');
    expect(formatStat('woba', 0.42)).toBe('.420');
  });

  it('formats fip to 2 decimals', () => {
    expect(formatStat('fip', 3.669)).toBe('3.67');
  });

  it('rounds ops_plus to integer', () => {
    expect(formatStat('ops_plus', 148.404)).toBe('148');
    expect(formatStat('ops_plus', 99.6)).toBe('100');
  });

  it('formats counting stats as integer', () => {
    expect(formatStat('home_runs', 25)).toBe('25');
    expect(formatStat('strikeouts', 70)).toBe('70');
  });

  it('returns em-dash for null/undefined', () => {
    expect(formatStat('woba', null)).toBe('—');
    expect(formatStat('avg', undefined)).toBe('—');
  });
});

describe('compareStatBetter', () => {
  it('descending stats: higher value wins', () => {
    expect(compareStatBetter('home_runs', 25, 18)).toBe('a');
    expect(compareStatBetter('avg', '.300', '.290')).toBe('b'.replace('b', 'a'));
    expect(compareStatBetter('woba', 0.4, 0.42)).toBe('b');
  });

  it('ascending stats: lower value wins', () => {
    expect(compareStatBetter('era', '2.50', '3.10')).toBe('a');
    expect(compareStatBetter('whip', 1.2, 0.9)).toBe('b');
    expect(compareStatBetter('fip', 3.5, 3.5)).toBe('tie');
  });

  it('returns null when either value is missing/unparseable', () => {
    expect(compareStatBetter('home_runs', null, 5)).toBeNull();
    expect(compareStatBetter('avg', '.300', undefined)).toBeNull();
    expect(compareStatBetter('woba', 'nope', 0.3)).toBeNull();
  });

  it('isAscendingStat tags ERA/WHIP/FIP only', () => {
    expect(isAscendingStat('era')).toBe(true);
    expect(isAscendingStat('whip')).toBe(true);
    expect(isAscendingStat('fip')).toBe(true);
    expect(isAscendingStat('avg')).toBe(false);
    expect(isAscendingStat('home_runs')).toBe(false);
  });
});
