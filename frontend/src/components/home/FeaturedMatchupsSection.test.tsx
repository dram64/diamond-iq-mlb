import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import { FeaturedMatchupsSection } from './FeaturedMatchupsSection';
import type { AppFeaturedItem, AppGame } from '@/types/app';

function makeFeatured(rank: number, gamePk: number, text: string): AppFeaturedItem {
  return {
    text,
    contentType: 'FEATURED',
    modelId: 'us.anthropic.claude-sonnet-4-6',
    generatedAt: new Date('2026-04-26T15:00:00Z'),
    gamePk,
    rank,
  };
}

function makeGame(id: number): AppGame {
  return {
    id,
    date: '2026-04-26',
    status: 'preview',
    detailedState: 'Scheduled',
    away: {
      id: 119,
      abbreviation: 'LAD',
      locationName: 'Los Angeles',
      teamName: 'Dodgers',
      fullName: 'Los Angeles Dodgers',
      logoPath: '',
      primaryColor: '#005A9C',
      secondaryColor: '',
    },
    home: {
      id: 137,
      abbreviation: 'SF',
      locationName: 'San Francisco',
      teamName: 'Giants',
      fullName: 'San Francisco Giants',
      logoPath: '',
      primaryColor: '#FD5A1E',
      secondaryColor: '',
    },
    awayScore: 0,
    homeScore: 0,
    startTimeUtc: '2026-04-26T22:00:00Z',
  };
}

function renderWithRouter(ui: React.ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
}

describe('FeaturedMatchupsSection', () => {
  it('renders skeleton state when loading', () => {
    renderWithRouter(
      <FeaturedMatchupsSection
        featured={[]}
        gamesByPk={new Map()}
        isLoading={true}
        isError={false}
        isEmpty={false}
      />,
    );
    expect(screen.getByTestId('featured-skeleton')).toBeInTheDocument();
  });

  it('renders 2 placeholder cards when empty', () => {
    renderWithRouter(
      <FeaturedMatchupsSection
        featured={[]}
        gamesByPk={new Map()}
        isLoading={false}
        isError={false}
        isEmpty={true}
      />,
    );
    expect(screen.getAllByText(/Sample preview/i)).toHaveLength(2);
  });

  it('renders 2 real cards from featured items', () => {
    // dedicated /live/:gameId page was retired. The cards still render
    // matchup headlines + AI body text.
    const featured = [
      makeFeatured(1, 3001, 'Featured one.'),
      makeFeatured(2, 3002, 'Featured two.'),
    ];
    const gamesByPk = new Map<number, AppGame>([
      [3001, makeGame(3001)],
      [3002, makeGame(3002)],
    ]);
    renderWithRouter(
      <FeaturedMatchupsSection
        featured={featured}
        gamesByPk={gamesByPk}
        isLoading={false}
        isError={false}
        isEmpty={false}
      />,
    );
    expect(screen.getByText('Featured one.')).toBeInTheDocument();
    expect(screen.getByText('Featured two.')).toBeInTheDocument();
    expect(screen.queryByText(/View game/i)).toBeNull();
  });

  it('handles missing game in gamesByPk via console.warn, no crash', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const featured = [makeFeatured(1, 9999, 'Orphan featured.')];
    renderWithRouter(
      <FeaturedMatchupsSection
        featured={featured}
        gamesByPk={new Map()}
        isLoading={false}
        isError={false}
        isEmpty={false}
      />,
    );
    expect(screen.getByText('Orphan featured.')).toBeInTheDocument();
    expect(warn).toHaveBeenCalledWith(expect.stringContaining('9999'));
    warn.mockRestore();
  });
});
