import { describe, expect, it } from 'vitest';

import { MLB_DIVISIONS, getMlbDivision, groupByDivision } from './mlbDivisions';

describe('MLB_DIVISIONS', () => {
  it('contains all six division ids', () => {
    const ids = MLB_DIVISIONS.map((d) => d.id).sort();
    expect(ids).toEqual([200, 201, 202, 203, 204, 205]);
  });

  it('canonical sort order: AL E/C/W then NL E/C/W', () => {
    const inOrder = [...MLB_DIVISIONS].sort((a, b) => a.sortKey - b.sortKey).map((d) => d.abbr);
    expect(inOrder).toEqual([
      'AL East',
      'AL Central',
      'AL West',
      'NL East',
      'NL Central',
      'NL West',
    ]);
  });
});

describe('getMlbDivision', () => {
  it('returns the matching division for a known id', () => {
    expect(getMlbDivision(201)?.abbr).toBe('AL East');
  });

  it('returns undefined for unknown ids', () => {
    expect(getMlbDivision(999)).toBeUndefined();
  });
});

describe('groupByDivision', () => {
  it('returns 6 groups in canonical order with teams bucketed correctly', () => {
    const teams = [
      { division_id: 201, team_id: 147 },
      { division_id: 200, team_id: 117 },
      { division_id: 201, team_id: 111 },
      { division_id: 204, team_id: 144 },
      { division_id: 203, team_id: 119 },
      { division_id: 205, team_id: 138 },
      { division_id: 202, team_id: 116 },
    ];
    const grouped = groupByDivision(teams);
    const abbrs = grouped.map((g) => g.division.abbr);
    expect(abbrs).toEqual(['AL East', 'AL Central', 'AL West', 'NL East', 'NL Central', 'NL West']);
    expect(grouped[0].teams).toHaveLength(2); // AL East got two
    expect(grouped[1].teams).toHaveLength(1); // AL Central got one
  });

  it('drops empty divisions from the output', () => {
    const teams = [{ division_id: 201, team_id: 147 }];
    const grouped = groupByDivision(teams);
    expect(grouped).toHaveLength(1);
    expect(grouped[0].division.abbr).toBe('AL East');
  });
});
