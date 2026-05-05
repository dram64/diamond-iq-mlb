import { describe, expect, it } from 'vitest';

import { todayUtcDate, yesterdayUtcDate } from './dateUtils';

describe('todayUtcDate', () => {
  it('returns YYYY-MM-DD format for the given UTC instant', () => {
    expect(todayUtcDate(new Date('2026-04-25T12:34:56Z'))).toBe('2026-04-25');
  });

  it('handles UTC midnight correctly', () => {
    expect(todayUtcDate(new Date('2026-04-25T00:00:00Z'))).toBe('2026-04-25');
  });

  it('handles the very last second of a UTC day', () => {
    expect(todayUtcDate(new Date('2026-04-25T23:59:59.999Z'))).toBe('2026-04-25');
  });

  it('uses the UTC day, not local time', () => {
    // 02:00 UTC on Apr 25 is the previous day in the western hemisphere.
    // todayUtcDate should still return the UTC day.
    expect(todayUtcDate(new Date('2026-04-25T02:00:00Z'))).toBe('2026-04-25');
  });

  it('uses the current time when no argument is given', () => {
    const result = todayUtcDate();
    expect(result).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });
});

describe('yesterdayUtcDate', () => {
  it('returns the day before todayUtcDate', () => {
    expect(yesterdayUtcDate(new Date('2026-04-25T12:00:00Z'))).toBe('2026-04-24');
  });

  it('handles month boundaries', () => {
    expect(yesterdayUtcDate(new Date('2026-05-01T12:00:00Z'))).toBe('2026-04-30');
  });

  it('handles year boundaries', () => {
    expect(yesterdayUtcDate(new Date('2027-01-01T12:00:00Z'))).toBe('2026-12-31');
  });

  it('handles leap day correctly', () => {
    expect(yesterdayUtcDate(new Date('2024-03-01T12:00:00Z'))).toBe('2024-02-29');
  });

  it('a moment after UTC midnight returns the day that just ended', () => {
    expect(yesterdayUtcDate(new Date('2026-04-25T00:00:01Z'))).toBe('2026-04-24');
  });
});
