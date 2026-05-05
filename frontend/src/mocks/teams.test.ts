import { describe, it, expect } from 'vitest';
import { TEAMS, teamBy } from './teams';

describe('teamBy', () => {
  it('returns the team for a known id', () => {
    const team = teamBy('STR');
    expect(team.city).toBe('Sierra');
    expect(team.abbr).toBe('STR');
  });

  it('throws for an unknown id', () => {
    expect(() => teamBy('ZZZ')).toThrow(/Unknown team/);
  });

  it('TEAMS has unique ids', () => {
    const ids = TEAMS.map((t) => t.id);
    expect(new Set(ids).size).toBe(ids.length);
  });
});
