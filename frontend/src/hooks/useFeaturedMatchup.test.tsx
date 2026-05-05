import { renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useFeaturedMatchup } from './useFeaturedMatchup';
import { makeQueryWrapper } from '@/test/queryWrapper';
import type { FeaturedMatchupResponse } from '@/types/featuredMatchup';

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}

function payload(): FeaturedMatchupResponse {
  return {
    data: {
      date: '2026-04-30',
      team_ids: [147, 119],
      teams: [
        {
          team_id: 147,
          team_name: 'Yankees',
          abbreviation: 'NYY',
          league: 'AL',
          wins: 21,
          losses: 10,
          games_back: '-',
          run_differential: 47,
          highlight_stats: { avg: '.265', ops: '.784', era: '3.21', whip: '1.18' },
        },
        {
          team_id: 119,
          team_name: 'Dodgers',
          abbreviation: 'LAD',
          league: 'NL',
          wins: 22,
          losses: 9,
          games_back: '-',
          run_differential: 58,
          highlight_stats: { avg: '.271', ops: '.812', era: '3.05', whip: '1.10' },
        },
      ],
      selection_reason: 'AL & NL standings leaders, deterministic by date',
    },
    meta: { season: 2026, timestamp: 'x', cache_max_age_seconds: 3600 },
  };
}

describe('useFeaturedMatchup', () => {
  let fetchMock: ReturnType<typeof vi.fn>;
  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  it('returns the matchup payload', async () => {
    fetchMock.mockResolvedValue(jsonResponse(payload()));
    const { Wrapper } = makeQueryWrapper();
    const { result } = renderHook(() => useFeaturedMatchup(), { wrapper: Wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.data.team_ids).toEqual([147, 119]);
    expect(result.current.data?.data.teams[0].league).toBe('AL');
    expect(result.current.data?.data.teams[1].league).toBe('NL');
  });

  it('reports isError on a 503 response', async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({ error: { code: 'data_not_yet_available', message: 'no rows' } }),
        { status: 503, headers: { 'Content-Type': 'application/json' } },
      ),
    );
    const { Wrapper } = makeQueryWrapper();
    const { result } = renderHook(() => useFeaturedMatchup(), { wrapper: Wrapper });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.status).toBe(503);
  });
});
