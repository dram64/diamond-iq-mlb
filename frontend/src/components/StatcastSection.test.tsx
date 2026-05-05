import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { StatcastSection } from './StatcastSection';
import type { ComparePlayer } from '@/types/compare';

function _hitter(personId: number, name: string, withStatcast: boolean): ComparePlayer {
  const base: ComparePlayer = {
    person_id: personId,
    metadata: { person_id: personId, full_name: name, primary_position_abbr: 'RF' },
    hitting: { team_id: 147, avg: '.290', home_runs: 12, ops: '.929' },
    pitching: null,
  };
  if (!withStatcast) return base;
  return {
    ...base,
    statcast: {
      person_id: personId,
      season: 2026,
      display_name: name,
      hitting: {
        xba: '.290',
        xslg: '.707',
        xwoba: '.466',
        avg_hit_speed: 94.7,
        max_hit_speed: 115.8,
        ev95_percent: 55.6,
        barrel_percent: 21.5,
        sweet_spot_percent: 38.9,
        sprint_speed: 26.8,
      },
      pitching: null,
      bat_tracking: {
        avg_bat_speed: 75.2,
        swing_length: 7.8,
        hard_swing_rate: 0.55,
        squared_up_per_swing: 0.21,
        blast_per_swing: 0.18,
      },
      batted_ball: {
        pull_rate: 0.49,
        straight_rate: 0.31,
        oppo_rate: 0.21,
      },
    },
  };
}

function _pitcher(personId: number, name: string): ComparePlayer {
  return {
    person_id: personId,
    metadata: { person_id: personId, full_name: name, primary_position_abbr: 'SP' },
    hitting: null,
    pitching: { team_id: 147, era: '3.11', strikeouts: 90, wins: 8 },
    statcast: {
      person_id: personId,
      season: 2026,
      hitting: null,
      pitching: {
        xera: 2.98,
        xba_against: '.200',
        whiff_percent: 26,
        chase_whiff_percent: 37.4,
        fastball_avg_speed: 95,
        fastball_avg_spin: 2263,
      },
      bat_tracking: null,
      batted_ball: null,
    },
  };
}

describe('StatcastSection', () => {
  it('renders nothing when no compared player has a statcast block', () => {
    const players = [_hitter(1, 'No Statcast A', false), _hitter(2, 'No Statcast B', false)];
    const { container } = render(<StatcastSection players={players} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders the Statcast header + footnote when at least one player has data', () => {
    const players = [_hitter(1, 'Has Statcast', true), _hitter(2, 'No Statcast', false)];
    render(<StatcastSection players={players} />);
    expect(screen.getByRole('heading', { name: /statcast/i })).toBeInTheDocument();
    // The phrase "Baseball Savant" appears in both the section header and the
    // footnote — assert at least one rendering rather than assuming uniqueness.
    expect(screen.getAllByText(/baseball savant/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/bat tracking metrics available from 2024\+/i)).toBeInTheDocument();
  });

  it('renders quality-of-contact + expected stats + bat tracking + spray for hitter rows', () => {
    const players = [_hitter(1, 'A', true), _hitter(2, 'B', true)];
    render(<StatcastSection players={players} />);
    expect(screen.getByText(/quality of contact/i)).toBeInTheDocument();
    expect(screen.getByText('Avg EV')).toBeInTheDocument();
    expect(screen.getByText('Max EV')).toBeInTheDocument();
    expect(screen.getByText('Barrel %')).toBeInTheDocument();
    expect(screen.getByText(/expected stats/i)).toBeInTheDocument();
    expect(screen.getByText('xBA')).toBeInTheDocument();
    expect(screen.getByText('xwOBA')).toBeInTheDocument();
    // "Bat tracking" appears as the sub-block title AND in the footnote —
    // both renderings are expected. We just need the title to exist.
    expect(screen.getByText('Bat tracking')).toBeInTheDocument();
    expect(screen.getByText('Avg bat speed')).toBeInTheDocument();
    expect(screen.getByText(/spray/i)).toBeInTheDocument();
    expect(screen.getByText('Pull %')).toBeInTheDocument();
  });

  it('renders pitcher arsenal block when a pitcher has statcast data', () => {
    const players = [_pitcher(519242, 'Sale'), _pitcher(543037, 'Cole')];
    render(<StatcastSection players={players} />);
    expect(screen.getByText(/pitcher arsenal/i)).toBeInTheDocument();
    expect(screen.getByText('Fastball velo')).toBeInTheDocument();
    expect(screen.getByText('Whiff %')).toBeInTheDocument();
    expect(screen.getByText('xERA')).toBeInTheDocument();
  });

  it('formats avg/max EV to one decimal and displays the values', () => {
    const players = [_hitter(1, 'Test', true), _hitter(2, 'Other', true)];
    render(<StatcastSection players={players} />);
    // 94.7 → "94.7", 115.8 → "115.8"
    expect(screen.getAllByText('94.7').length).toBeGreaterThan(0);
    expect(screen.getAllByText('115.8').length).toBeGreaterThan(0);
  });

  it('formats rate-of-1 fields (pull_rate=0.49) as "49.0%"', () => {
    const players = [_hitter(1, 'Test', true), _hitter(2, 'Other', true)];
    render(<StatcastSection players={players} />);
    expect(screen.getAllByText('49.0%').length).toBeGreaterThan(0);
  });

  it('formats fastball spin as integer (no decimal)', () => {
    const players = [_pitcher(519242, 'Sale'), _pitcher(543037, 'Cole')];
    render(<StatcastSection players={players} />);
    expect(screen.getAllByText('2263').length).toBeGreaterThan(0);
  });

  it('handles null fields gracefully — renders em-dash for missing data', () => {
    const player: ComparePlayer = {
      person_id: 1,
      metadata: { person_id: 1, full_name: 'Sparse', primary_position_abbr: 'RF' },
      hitting: { team_id: 147, avg: '.290' },
      pitching: null,
      statcast: {
        person_id: 1,
        season: 2026,
        hitting: { xba: '.290', avg_hit_speed: null }, // most fields missing
        pitching: null,
        bat_tracking: null,
        batted_ball: null,
      },
    };
    const other: ComparePlayer = _hitter(2, 'Full', true);
    render(<StatcastSection players={[player, other]} />);
    // Sparse hitter should still render in the row but avg_hit_speed shows —.
    expect(screen.getAllByText('—').length).toBeGreaterThan(0);
  });
});
