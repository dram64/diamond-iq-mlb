import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { DailyRecapSection } from './DailyRecapSection';
import type { AppContentItem, AppGame } from '@/types/app';

function makeRecap(gamePk: number, text: string): AppContentItem {
  return {
    text,
    contentType: 'RECAP',
    modelId: 'us.anthropic.claude-sonnet-4-6',
    generatedAt: new Date('2026-04-26T15:00:00Z'),
    gamePk,
  };
}

function makeGame(id: number): AppGame {
  return {
    id,
    date: '2026-04-25',
    status: 'final',
    detailedState: 'Final',
    away: {
      id: 111,
      abbreviation: 'BOS',
      locationName: 'Boston',
      teamName: 'Red Sox',
      fullName: 'Boston Red Sox',
      logoPath: '',
      primaryColor: '#000',
      secondaryColor: '',
    },
    home: {
      id: 147,
      abbreviation: 'NYY',
      locationName: 'New York',
      teamName: 'Yankees',
      fullName: 'New York Yankees',
      logoPath: '',
      primaryColor: '#000',
      secondaryColor: '',
    },
    awayScore: 3,
    homeScore: 5,
    startTimeUtc: '2026-04-25T19:00:00Z',
  };
}

describe('DailyRecapSection', () => {
  it('renders a skeleton while loading', () => {
    render(
      <DailyRecapSection
        recap={[]}
        gamesByPk={new Map()}
        isLoading={true}
        isError={false}
        isEmpty={false}
      />,
    );
    expect(screen.getByTestId('recap-skeleton')).toBeInTheDocument();
  });

  it('renders placeholder copy on error with API-unavailable footer', () => {
    render(
      <DailyRecapSection
        recap={[]}
        gamesByPk={new Map()}
        isLoading={false}
        isError={true}
        isEmpty={false}
      />,
    );
    expect(screen.getByText(/API unavailable/i)).toBeInTheDocument();
  });

  it('renders placeholder copy on empty with sample-preview footer', () => {
    render(
      <DailyRecapSection
        recap={[]}
        gamesByPk={new Map()}
        isLoading={false}
        isError={false}
        isEmpty={true}
      />,
    );
    expect(screen.getByText(/Sample preview/i)).toBeInTheDocument();
  });

  it('renders one card per recap with matchup and AI text', () => {
    const recap = [makeRecap(1001, 'Para one.\n\nPara two.')];
    const gamesByPk = new Map<number, AppGame>([[1001, makeGame(1001)]]);
    render(
      <DailyRecapSection
        recap={recap}
        gamesByPk={gamesByPk}
        isLoading={false}
        isError={false}
        isEmpty={false}
      />,
    );
    expect(screen.getByText('Para one.')).toBeInTheDocument();
    expect(screen.getByText('Para two.')).toBeInTheDocument();
    expect(screen.getByText('Boston Red Sox')).toBeInTheDocument();
    expect(screen.getByText('New York Yankees')).toBeInTheDocument();
  });
});
