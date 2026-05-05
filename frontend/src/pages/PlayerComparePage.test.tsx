import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import type { ReactElement } from 'react';

import { PlayerComparePage } from './PlayerComparePage';
import { makeQueryWrapper } from '@/test/queryWrapper';
import type { CompareResponse } from '@/types/compare';

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
            bat_side: 'R',
            pitch_hand: 'R',
            height: '6\' 7"',
            weight: 282,
          },
          hitting: {
            team_id: 147,
            avg: '.230',
            home_runs: 10,
            rbi: 18,
            ops: '.929',
            woba: 0.399,
            ops_plus: 148,
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
            ops_plus: 225,
          },
          pitching: null,
        },
      ],
    },
    meta: { season: 2026, timestamp: '2026-04-30T00:00:00Z', cache_max_age_seconds: 300 },
  };
}

function renderPage(ui: ReactElement, initialEntries: string[] = ['/compare-players']) {
  const { Wrapper } = makeQueryWrapper();
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <Wrapper>{ui}</Wrapper>
    </MemoryRouter>,
  );
}

describe('PlayerComparePage', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders the page header, search input, and quick-pick presets', () => {
    fetchMock.mockReturnValue(new Promise(() => {}));
    renderPage(<PlayerComparePage />);
    expect(screen.getByRole('heading', { name: /player compare/i })).toBeInTheDocument();
    expect(screen.getByRole('searchbox', { name: /add a player by name/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /judge vs alvarez/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /sale vs soriano/i })).toBeInTheDocument();
  });

  it('fires a default comparison fetch on mount', async () => {
    fetchMock.mockResolvedValue(jsonResponse(hitterPayload()));
    renderPage(<PlayerComparePage />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const url = fetchMock.mock.calls[0][0] as string;
    expect(url).toContain('/api/players/compare');
  });

  it('renders side-by-side hitter comparison on success with lg headshots', async () => {
    fetchMock.mockResolvedValue(jsonResponse(hitterPayload()));
    renderPage(<PlayerComparePage />);
    // The name appears twice: once in the picker chip, once in the comparison
    // panel header. We just need at least one rendering.
    await waitFor(() => expect(screen.getAllByText('Aaron Judge').length).toBeGreaterThan(0));
    expect(screen.getAllByText('Yordan Alvarez').length).toBeGreaterThan(0);
    // table below (AVG row in the Hitting group).
    expect(screen.getByText('xwOBA')).toBeInTheDocument();
    expect(screen.getByText('Numerical detail')).toBeInTheDocument();
    expect(screen.getAllByText('AVG').length).toBeGreaterThan(0);
    // size="lg" headshot is the comparison-panel one (the picker chip uses size="sm").
    const judgeImgs = screen.getAllByAltText('Aaron Judge') as HTMLImageElement[];
    const lg = judgeImgs.find((img) => img.width === 96);
    expect(lg).toBeDefined();
    expect(lg?.src).toContain('img.mlbstatic.com');
  });

  it('reads ?ids= from the URL and calls the API with those ids', async () => {
    fetchMock.mockResolvedValue(jsonResponse(hitterPayload()));
    renderPage(<PlayerComparePage />, ['/compare-players?ids=545361,621566']);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const url = fetchMock.mock.calls[0][0] as string;
    expect(url).toContain('545361');
    expect(url).toContain('621566');
  });

  it('renders an error banner with retry on API failure', async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ error: { code: 'oops', message: 'down' } }), {
        status: 500,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    renderPage(<PlayerComparePage />);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument(),
    );
  });

  it('clicking a different matchup tab triggers a new fetch', async () => {
    fetchMock.mockResolvedValue(jsonResponse(hitterPayload()));
    renderPage(<PlayerComparePage />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole('tab', { name: /sale vs soriano/i }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const secondUrl = fetchMock.mock.calls[1][0] as string;
    expect(secondUrl).toContain('519242');
    expect(secondUrl).toContain('667755');
  });

  it('renders four players when ?ids has four entries', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        data: {
          players: [
            {
              person_id: 1,
              metadata: { person_id: 1, full_name: 'Player A', primary_position_abbr: 'RF' },
              hitting: { team_id: 147, avg: '.300', home_runs: 10, rbi: 30, ops: '.900' },
              pitching: null,
            },
            {
              person_id: 2,
              metadata: { person_id: 2, full_name: 'Player B', primary_position_abbr: 'CF' },
              hitting: { team_id: 117, avg: '.310', home_runs: 12, rbi: 28, ops: '.950' },
              pitching: null,
            },
            {
              person_id: 3,
              metadata: { person_id: 3, full_name: 'Player C', primary_position_abbr: 'LF' },
              hitting: { team_id: 144, avg: '.290', home_runs: 8, rbi: 25, ops: '.870' },
              pitching: null,
            },
            {
              person_id: 4,
              metadata: { person_id: 4, full_name: 'Player D', primary_position_abbr: '1B' },
              hitting: { team_id: 121, avg: '.275', home_runs: 9, rbi: 27, ops: '.860' },
              pitching: null,
            },
          ],
        },
        meta: { season: 2026, timestamp: 'x', cache_max_age_seconds: 300 },
      }),
    );
    renderPage(<PlayerComparePage />, ['/compare-players?ids=1,2,3,4']);
    // Names render twice (picker chip + comparison panel) — assert ≥ 1 each.
    await waitFor(() => expect(screen.getAllByText('Player A').length).toBeGreaterThan(0));
    expect(screen.getAllByText('Player B').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Player C').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Player D').length).toBeGreaterThan(0);
    // Picker chip + comparison-panel × buttons — 4 each = 8 total when count > MIN.
    const removeButtons = screen.getAllByRole('button', { name: /remove/i });
    expect(removeButtons.length).toBeGreaterThanOrEqual(4);
  });

  it('search picker fires /api/players/search and adds picked id to the URL', async () => {
    // First fetch: the default compare for the fallback ids.
    // Subsequent fetches: search results, then a re-compare with the new id.
    const compareResp = jsonResponse(hitterPayload());
    const searchResp = jsonResponse({
      data: {
        query: 'sale',
        results: [
          {
            person_id: 519242,
            full_name: 'Chris Sale',
            primary_position_abbr: 'SP',
            primary_number: '41',
          },
        ],
        count: 1,
      },
      meta: { season: 2026, timestamp: 'x', cache_max_age_seconds: 60 },
    });

    fetchMock.mockImplementation((url: string) => {
      if (url.includes('/api/players/search')) return Promise.resolve(searchResp.clone());
      return Promise.resolve(compareResp.clone());
    });

    renderPage(<PlayerComparePage />);
    await waitFor(() => expect(screen.getAllByText('Aaron Judge').length).toBeGreaterThan(0));

    const input = screen.getByRole('searchbox', { name: /add a player by name/i });
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: 'sale' } });

    // The search dropdown shows after debounce.
    await waitFor(() => expect(screen.getByText('Chris Sale')).toBeInTheDocument(), {
      timeout: 1000,
    });
    // The search request fired against /api/players/search.
    const searchCalls = fetchMock.mock.calls.filter((c) =>
      String(c[0]).includes('/api/players/search'),
    );
    expect(searchCalls.length).toBeGreaterThanOrEqual(1);

    // Picking the result should have appended Sale's id to the URL ids list.
    fireEvent.click(screen.getByRole('option', { name: /chris sale/i }));
    await waitFor(() =>
      expect(
        fetchMock.mock.calls
          .map((c) => String(c[0]))
          .some((u) => u.includes('/api/players/compare') && u.includes('519242')),
      ).toBe(true),
    );
  });

  it('renders accolades chip row when awards block is supplied', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        data: {
          players: [
            {
              person_id: 592450,
              metadata: { person_id: 592450, full_name: 'Aaron Judge', primary_position_abbr: 'RF' },
              hitting: { team_id: 147, avg: '.300', home_runs: 10, ops: '.900' },
              pitching: null,
              awards: {
                person_id: 592450,
                total_awards: 5,
                all_star_count: 3,
                all_star_years: [2017, 2018, 2022],
                mvp_count: 1,
                mvp_years: [2024],
                cy_young_count: 0,
                cy_young_years: [],
                rookie_of_the_year_count: 1,
                rookie_of_the_year_years: [2017],
                gold_glove_count: 0,
                gold_glove_years: [],
                silver_slugger_count: 0,
                silver_slugger_years: [],
                world_series_count: 0,
                world_series_years: [],
              },
            },
            {
              person_id: 670541,
              metadata: { person_id: 670541, full_name: 'Yordan Alvarez', primary_position_abbr: 'DH' },
              hitting: { team_id: 117, avg: '.330', home_runs: 14, ops: '1.000' },
              pitching: null,
              awards: null,
            },
          ],
        },
        meta: { season: 2026, timestamp: 'x', cache_max_age_seconds: 300 },
      }),
    );
    renderPage(<PlayerComparePage />);
    await waitFor(() => expect(screen.getAllByText('Aaron Judge').length).toBeGreaterThan(0));
    // MVP / ROY / AS chips render with the correct counts.
    expect(screen.getByText('MVP')).toBeInTheDocument();
    expect(screen.getByText('ROY')).toBeInTheDocument();
    expect(screen.getByText('AS')).toBeInTheDocument();
    // Multiple ×1 chips (MVP and ROY both have one) — both visible.
    expect(screen.getAllByText('×1').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText('×3')).toBeInTheDocument();
  });
});
