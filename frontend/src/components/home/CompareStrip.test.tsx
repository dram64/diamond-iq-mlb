import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { CompareStrip } from './CompareStrip';
import { makeQueryWrapper } from '@/test/queryWrapper';
import type { CompareResponse } from '@/types/compare';
import type { ReactElement } from 'react';

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
}

function hitterPayload(): CompareResponse {
  return {
    data: {
      players: [
        {
          person_id: 592450,
          metadata: {
            person_id: 592450,
            full_name: 'Aaron Judge',
            primary_position_abbr: 'RF',
          },
          hitting: {
            team_id: 147,
            avg: '.230',
            home_runs: 10,
            rbi: 18,
            ops: '.929',
            woba: 0.399,
            ops_plus: 148.404,
          },
          pitching: null,
        },
        {
          person_id: 670541,
          metadata: {
            person_id: 670541,
            full_name: 'Yordan Alvarez',
            primary_position_abbr: 'DH',
          },
          hitting: {
            team_id: 117,
            avg: '.358',
            home_runs: 11,
            rbi: 26,
            ops: '1.220',
            woba: 0.503,
            ops_plus: 225.055,
          },
          pitching: null,
        },
      ],
    },
    meta: { season: 2026, timestamp: '2026-04-27T00:00:00Z', cache_max_age_seconds: 300 },
  };
}

function bothNullPayload(): CompareResponse {
  return {
    data: {
      players: [
        {
          person_id: 1,
          metadata: { person_id: 1, full_name: 'Player A' },
          hitting: null,
          pitching: null,
        },
        {
          person_id: 2,
          metadata: { person_id: 2, full_name: 'Player B' },
          hitting: null,
          pitching: null,
        },
      ],
    },
    meta: { season: 2026, timestamp: 'x', cache_max_age_seconds: 300 },
  };
}

function mismatchPayload(): CompareResponse {
  return {
    data: {
      players: [
        {
          person_id: 1,
          metadata: { person_id: 1, full_name: 'A Hitter', primary_position_abbr: 'RF' },
          hitting: { team_id: 147, avg: '.300', home_runs: 5 },
          pitching: null,
        },
        {
          person_id: 2,
          metadata: { person_id: 2, full_name: 'A Pitcher', primary_position_abbr: 'P' },
          hitting: null,
          pitching: { team_id: 144, era: '2.50', strikeouts: 60 },
        },
      ],
    },
    meta: { season: 2026, timestamp: 'x', cache_max_age_seconds: 300 },
  };
}

function renderInWrapper(ui: ReactElement) {
  const { Wrapper } = makeQueryWrapper();
  return render(<Wrapper>{ui}</Wrapper>);
}

describe('CompareStrip', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders the four featured matchup tabs', () => {
    fetchMock.mockReturnValue(new Promise(() => {})); // never resolves
    renderInWrapper(<CompareStrip />);
    expect(screen.getByRole('tab', { name: /judge vs alvarez/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /trout vs olson/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /sale vs soriano/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /schlittler vs wrobleski/i })).toBeInTheDocument();
  });

  it('renders skeleton during initial fetch', () => {
    fetchMock.mockReturnValue(new Promise(() => {}));
    renderInWrapper(<CompareStrip />);
    // Skeleton has many empty divs; check that no player names render yet.
    expect(screen.queryByText('Aaron Judge')).toBeNull();
  });

  it('renders side-by-side hitter comparison on success', async () => {
    fetchMock.mockResolvedValue(jsonResponse(hitterPayload()));
    renderInWrapper(<CompareStrip />);
    await waitFor(() => expect(screen.getByText('Aaron Judge')).toBeInTheDocument());
    expect(screen.getByText('Yordan Alvarez')).toBeInTheDocument();
    // Hitting stat labels rendered.
    expect(screen.getByText('AVG')).toBeInTheDocument();
    expect(screen.getByText('wOBA')).toBeInTheDocument();
    // Formatted values rendered.
    expect(screen.getByText('.503')).toBeInTheDocument();
    const judgeImg = screen.getByAltText('Aaron Judge') as HTMLImageElement;
    expect(judgeImg.src).toContain('img.mlbstatic.com');
    expect(judgeImg.src).toContain('/v1/people/592450/headshot/67/current');
  });

  it('renders error state with retry button when API fails', async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ error: { code: 'oops', message: 'down' } }), {
        status: 500,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    renderInWrapper(<CompareStrip />);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument(),
    );
  });

  it('renders insufficient-data fallback when both groups are null', async () => {
    fetchMock.mockResolvedValue(jsonResponse(bothNullPayload()));
    renderInWrapper(<CompareStrip />);
    await waitFor(() =>
      expect(screen.getByText(/insufficient season data/i)).toBeInTheDocument(),
    );
  });

  it('renders incomparable-types fallback when one is hitter and one is pitcher', async () => {
    fetchMock.mockResolvedValue(jsonResponse(mismatchPayload()));
    renderInWrapper(<CompareStrip />);
    await waitFor(() =>
      expect(screen.getByText(/player types incomparable/i)).toBeInTheDocument(),
    );
  });

  it('clicking a tab swaps the comparison and triggers a new fetch', async () => {
    fetchMock.mockResolvedValue(jsonResponse(hitterPayload()));
    renderInWrapper(<CompareStrip />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole('tab', { name: /sale vs soriano/i }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    // Second call hits a different ids set.
    const secondUrl = fetchMock.mock.calls[1][0] as string;
    expect(secondUrl).toContain('519242');
    expect(secondUrl).toContain('667755');
  });
});
