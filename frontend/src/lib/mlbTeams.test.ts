import { describe, expect, it } from 'vitest';

import { getAllMlbTeams, getMlbTeam, getMlbTeamRequired } from './mlbTeams';

const HEX_RE = /^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/;

describe('mlbTeams table', () => {
  it('contains exactly 30 teams', () => {
    expect(getAllMlbTeams()).toHaveLength(30);
  });

  it('every team has a unique id', () => {
    const ids = getAllMlbTeams().map((t) => t.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('every team has a unique abbreviation', () => {
    const abbrs = getAllMlbTeams().map((t) => t.abbreviation);
    expect(new Set(abbrs).size).toBe(abbrs.length);
  });

  it('every team has non-empty primary and secondary colors', () => {
    for (const t of getAllMlbTeams()) {
      expect(t.primaryColor.length, `${t.fullName} primary`).toBeGreaterThan(0);
      expect(t.secondaryColor.length, `${t.fullName} secondary`).toBeGreaterThan(0);
    }
  });

  it('every color is a valid hex (3 or 6 digits)', () => {
    for (const t of getAllMlbTeams()) {
      expect(t.primaryColor, `${t.fullName} primary`).toMatch(HEX_RE);
      expect(t.secondaryColor, `${t.fullName} secondary`).toMatch(HEX_RE);
    }
  });

  it('splits 15 AL / 15 NL', () => {
    const al = getAllMlbTeams().filter((t) => t.league === 'AL').length;
    const nl = getAllMlbTeams().filter((t) => t.league === 'NL').length;
    expect(al).toBe(15);
    expect(nl).toBe(15);
  });

  it('5 teams per (league, division) pair', () => {
    const counts = new Map<string, number>();
    for (const t of getAllMlbTeams()) {
      const key = `${t.league}-${t.division}`;
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    for (const [key, n] of counts) {
      expect(n, key).toBe(5);
    }
    expect(counts.size).toBe(6);
  });
});

describe('getMlbTeam', () => {
  it('returns the team for a known id', () => {
    const team = getMlbTeam(147);
    expect(team?.fullName).toBe('New York Yankees');
    expect(team?.abbreviation).toBe('NYY');
  });

  it('returns undefined for an unknown id', () => {
    expect(getMlbTeam(999_999)).toBeUndefined();
  });
});

describe('getMlbTeamRequired', () => {
  it('returns the team for a known id', () => {
    expect(getMlbTeamRequired(140).fullName).toBe('Texas Rangers');
  });

  it('throws for an unknown id', () => {
    expect(() => getMlbTeamRequired(999_999)).toThrow(/Unknown MLB team/);
  });
});
