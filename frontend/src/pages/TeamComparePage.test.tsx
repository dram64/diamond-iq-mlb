import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import type { ReactElement } from 'react';

import { TeamComparePage } from './TeamComparePage';
import { makeQueryWrapper } from '@/test/queryWrapper';
import type { TeamCompareResponse } from '@/types/teamStats';

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
}

function teamComparePayload(): TeamCompareResponse {
  return {
    data: {
      season: 2026,
      teams: [
        {
          team_id: 147,
          team_name: 'New York Yankees',
          season: 2026,
          hitting: {
            games_played: 31,
            avg: '.229',
            home_runs: 48,
            rbi: 145,
            obp: '.324',
            slg: '.424',
            ops: '.748',
            stolen_bases: 32,
          },
          pitching: {
            era: '3.11',
            whip: '1.14',
            strikeouts: 268,
            wins: 20,
            saves: 9,
            opp_avg: '.222',
          },
        },
        {
          team_id: 121,
          team_name: 'New York Mets',
          season: 2026,
          hitting: {
            games_played: 30,
            avg: '.224',
            home_runs: 23,
            rbi: 94,
            obp: '.289',
            slg: '.341',
            ops: '.630',
            stolen_bases: 16,
          },
          pitching: {
            era: '3.95',
            whip: '1.28',
            strikeouts: 270,
            wins: 10,
            saves: 2,
            opp_avg: '.233',
          },
        },
      ],
    },
    meta: { season: 2026, timestamp: '2026-04-30T00:00:00Z', cache_max_age_seconds: 900 },
  };
}

function renderPage(ui: ReactElement, initialEntries: string[] = ['/compare-teams']) {
  const { Wrapper } = makeQueryWrapper();
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <Wrapper>{ui}</Wrapper>
    </MemoryRouter>,
  );
}

describe('TeamComparePage', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders the page header and two team-select dropdowns', () => {
    fetchMock.mockReturnValue(new Promise(() => {}));
    renderPage(<TeamComparePage />);
    expect(screen.getByRole('heading', { name: /team compare/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/team a/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/team b/i)).toBeInTheDocument();
  });

  it('fires a default comparison fetch on mount', async () => {
    fetchMock.mockResolvedValue(jsonResponse(teamComparePayload()));
    renderPage(<TeamComparePage />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const url = fetchMock.mock.calls[0][0] as string;
    expect(url).toContain('/api/teams/compare?ids=');
  });

  it('renders side-by-side team comparison on success', async () => {
    fetchMock.mockResolvedValue(jsonResponse(teamComparePayload()));
    renderPage(<TeamComparePage />);
    // Names appear in header card, picker dropdowns, radar legend + table
    // header — assert at least one render rather than exactly one.
    await waitFor(() => expect(screen.getAllByText('New York Yankees').length).toBeGreaterThan(0));
    expect(screen.getAllByText('New York Mets').length).toBeGreaterThan(0);
    // table grouped by team batting / team pitching.
    expect(screen.getByText('Team OPS')).toBeInTheDocument();
    expect(screen.getByText('Team batting')).toBeInTheDocument();
    expect(screen.getByText('Team pitching')).toBeInTheDocument();
    expect(screen.getByText('Numerical detail')).toBeInTheDocument();
    // Detail-table stat labels (OPS appears both as radar axis "Team OPS"
    // and as detail-table row label "OPS"; assert ≥ 1).
    expect(screen.getAllByText('OPS').length).toBeGreaterThan(0);
    expect(screen.getAllByText('ERA').length).toBeGreaterThan(0);
    expect(screen.getAllByText('SB').length).toBeGreaterThan(0);
  });

  it('reads ?ids= from the URL and calls the API with those ids', async () => {
    fetchMock.mockResolvedValue(jsonResponse(teamComparePayload()));
    renderPage(<TeamComparePage />, ['/compare-teams?ids=117,119']);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const url = fetchMock.mock.calls[0][0] as string;
    expect(url).toContain('117');
    expect(url).toContain('119');
  });

  it('changing a team-select triggers a new fetch', async () => {
    fetchMock.mockResolvedValue(jsonResponse(teamComparePayload()));
    renderPage(<TeamComparePage />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const teamA = screen.getByLabelText(/team a/i) as HTMLSelectElement;
    fireEvent.change(teamA, { target: { value: '117' } }); // Astros
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const secondUrl = fetchMock.mock.calls[1][0] as string;
    expect(secondUrl).toContain('117');
  });

  it('renders an error banner with retry on API failure', async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ error: { code: 'oops', message: 'down' } }), {
        status: 500,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    renderPage(<TeamComparePage />);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument(),
    );
  });
});
