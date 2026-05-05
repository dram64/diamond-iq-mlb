import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { LeadersList } from './LeadersList';
import { makeQueryWrapper } from '@/test/queryWrapper';
import type { LeadersResponse } from '@/types/leaders';

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
}

function payload(): LeadersResponse {
  return {
    data: {
      group: 'hitting',
      stat: 'hr',
      field: 'home_runs',
      direction: 'desc',
      limit: 2,
      leaders: [
        {
          person_id: 592450,
          full_name: 'Aaron Judge',
          rank: 1,
          team_id: 147,
          home_runs: 25,
          avg: '.320',
          ops: '1.030',
          woba: 0.42,
        },
        {
          person_id: 514888,
          full_name: 'Jose Altuve',
          rank: 2,
          team_id: 117,
          home_runs: 18,
          avg: '.290',
          ops: '.870',
          woba: 0.36,
        },
      ],
    },
    meta: { season: 2026, timestamp: '2026-04-27T00:00:00Z', cache_max_age_seconds: 600 },
  };
}

function renderInWrapper(ui: React.ReactElement) {
  const { Wrapper } = makeQueryWrapper();
  return render(<MemoryRouter><Wrapper>{ui}</Wrapper></MemoryRouter>);
}

const STANDARD_PROPS = {
  title: 'Batting',
  group: 'hitting' as const,
  primaryStat: 'hr',
  secondaryStats: ['avg', 'ops', 'woba'] as const,
  cols: ['', '', 'HR', 'AVG', 'OPS', 'wOBA'] as const,
  linkTo: '/stats',
};

describe('LeadersList', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders skeleton placeholders during initial load', () => {
    fetchMock.mockReturnValue(new Promise(() => {})); // never resolves
    renderInWrapper(<LeadersList {...STANDARD_PROPS} />);
    expect(screen.getAllByRole('generic', { hidden: true }).length).toBeGreaterThan(0);
    expect(screen.queryByText('Aaron Judge')).toBeNull();
  });

  it('renders the ranked leader rows on success with formatted stats', async () => {
    fetchMock.mockResolvedValue(jsonResponse(payload()));
    renderInWrapper(<LeadersList {...STANDARD_PROPS} />);
    await waitFor(() => expect(screen.getByText('Aaron Judge')).toBeInTheDocument());
    expect(screen.getByText('Jose Altuve')).toBeInTheDocument();
    // Primary stat (HR) shown as integer
    expect(screen.getByText('25')).toBeInTheDocument();
    // wOBA shown stripped of leading zero
    expect(screen.getByText('.420')).toBeInTheDocument();
    expect(screen.getByText('.320')).toBeInTheDocument();
    const judgeImg = screen.getByAltText('Aaron Judge') as HTMLImageElement;
    expect(judgeImg.src).toContain('img.mlbstatic.com');
    expect(judgeImg.src).toContain('/v1/people/592450/headshot/67/current');
  });

  it('renders empty state when leaders array is empty', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        data: {
          group: 'hitting',
          stat: 'hr',
          field: 'home_runs',
          direction: 'desc',
          limit: 5,
          leaders: [],
        },
        meta: { season: 2026, timestamp: 'x', cache_max_age_seconds: 600 },
      }),
    );
    renderInWrapper(<LeadersList {...STANDARD_PROPS} />);
    await waitFor(() => expect(screen.getByText(/no leaders available/i)).toBeInTheDocument());
  });

  it('renders error state with retry button when API fails', async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ error: { code: 'oops', message: 'down' } }), {
        status: 500,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    renderInWrapper(<LeadersList {...STANDARD_PROPS} />);
    await waitFor(() => expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument());
  });

  it('Retry click triggers another fetch', async () => {
    let call = 0;
    fetchMock.mockImplementation(() => {
      call += 1;
      if (call === 1) {
        return Promise.resolve(
          new Response(JSON.stringify({ error: { code: 'oops', message: 'down' } }), {
            status: 500,
            headers: { 'Content-Type': 'application/json' },
          }),
        );
      }
      return Promise.resolve(jsonResponse(payload()));
    });

    renderInWrapper(<LeadersList {...STANDARD_PROPS} />);
    const retry = await screen.findByRole('button', { name: /retry/i });
    fireEvent.click(retry);
    await waitFor(() => expect(screen.getByText('Aaron Judge')).toBeInTheDocument());
  });
});
