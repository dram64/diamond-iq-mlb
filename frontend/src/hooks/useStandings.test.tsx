import { renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useStandings } from './useStandings';
import { makeQueryWrapper } from '@/test/queryWrapper';

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
}

function payload(season: number, teamCount: number) {
  const teams = Array.from({ length: teamCount }, (_, i) => ({
    team_id: 100 + i,
    team_name: `Team ${i}`,
    division_id: 201,
    league_id: 103,
    wins: 18,
    losses: 10,
    pct: '.643',
    games_back: '-',
    streak_code: 'W1',
    run_differential: 10,
    division_rank: '1', // string upstream — coerced on parse
    league_rank: '1',
  }));
  return {
    data: { season, teams },
    meta: { season, timestamp: '2026-04-27T00:00:00Z', cache_max_age_seconds: 900 },
  };
}

describe('useStandings', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('returns the standings payload on success and coerces ranks to numbers', async () => {
    fetchMock.mockResolvedValue(jsonResponse(payload(2026, 30)));
    const { Wrapper } = makeQueryWrapper();
    const { result } = renderHook(() => useStandings(2026), { wrapper: Wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.data.teams).toHaveLength(30);
    // Boundary coercion: division_rank / league_rank are numbers, not strings.
    const t = result.current.data!.data.teams[0];
    expect(typeof t.division_rank).toBe('number');
    expect(typeof t.league_rank).toBe('number');
  });

  it('reports isLoading=true on initial mount', () => {
    fetchMock.mockReturnValue(new Promise(() => {}));
    const { Wrapper } = makeQueryWrapper();
    const { result } = renderHook(() => useStandings(2026), { wrapper: Wrapper });
    expect(result.current.isLoading).toBe(true);
  });

  it('reports isError=true on a 5xx response', async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ error: { code: 'oops', message: 'down' } }), {
        status: 500,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    const { Wrapper } = makeQueryWrapper();
    const { result } = renderHook(() => useStandings(2026), { wrapper: Wrapper });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.name).toBe('ApiError');
  });

  it('uses the season as part of the queryKey for cache disambiguation', async () => {
    fetchMock.mockResolvedValue(jsonResponse(payload(2025, 30)));
    const { Wrapper } = makeQueryWrapper();
    const { rerender } = renderHook(
      ({ season }: { season: number }) => useStandings(season),
      { wrapper: Wrapper, initialProps: { season: 2025 } },
    );
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    rerender({ season: 2026 });
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  });

  it('hits the correct API path including season', async () => {
    fetchMock.mockResolvedValue(jsonResponse(payload(2026, 30)));
    const { Wrapper } = makeQueryWrapper();
    renderHook(() => useStandings(2026), { wrapper: Wrapper });
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const url = fetchMock.mock.calls[0][0] as string;
    expect(url).toContain('/api/standings/2026');
  });
});
