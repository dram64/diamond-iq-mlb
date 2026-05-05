import { describe, it, expect } from 'vitest';
import { formatBA, formatRunDiff, inningArrow } from './format';

describe('formatBA', () => {
  it('drops the leading zero from a batting average', () => {
    expect(formatBA(0.326)).toBe('.326');
  });

  it('clamps values outside [0, 1]', () => {
    expect(formatBA(1.5)).toBe('1.000');
    expect(formatBA(-0.1)).toBe('.000');
  });

  it('handles NaN gracefully', () => {
    expect(formatBA(Number.NaN)).toBe('.000');
  });
});

describe('formatRunDiff', () => {
  it('prepends + for positive values', () => {
    expect(formatRunDiff(112)).toBe('+112');
  });

  it('keeps the minus sign for negatives', () => {
    expect(formatRunDiff(-14)).toBe('-14');
  });

  it('renders zero without a sign', () => {
    expect(formatRunDiff(0)).toBe('0');
  });
});

describe('inningArrow', () => {
  it('maps top/bot to arrow glyphs', () => {
    expect(inningArrow('top')).toBe('▲');
    expect(inningArrow('bot')).toBe('▼');
  });
});
