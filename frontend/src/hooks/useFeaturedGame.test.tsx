import { renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useFeaturedGame } from './useFeaturedGame';
import { makeQueryWrapper } from '@/test/queryWrapper';
import type { FeaturedGameResponse } from '@/types/featuredGame';

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function payload(): FeaturedGameResponse {
  return {
    data: {
      date: '2026-04-30',
      game_pk: 823795,
      status: 'preview',
      detailed_state: 'Pre-Game',
      start_time_utc: '2026-04-30T17:40:00Z',
      venue: 'American Family Field',
      away: {
        team_id: 109,
        team_name: 'Arizona Diamondbacks',
        abbreviation: 'AZ',
        wins: 13,
        losses: 17,
        run_differential: -22,
        probable_pitcher: { id: 605288, full_name: 'Adrian Houser' },
      },
      home: {
        team_id: 158,
        team_name: 'Milwaukee Brewers',
        abbreviation: 'MIL',
        wins: 18,
        losses: 12,
        run_differential: 15,
        probable_pitcher: { id: 641835, full_name: 'Tim Mayza' },
      },
      selection_reason: "Date-seeded among today's non-final games",
    },
    meta: { season: 2026, timestamp: 'x', cache_max_age_seconds: 180 },
  };
}

describe('useFeaturedGame', () => {
  let fetchMock: ReturnType<typeof vi.fn>;
  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  it('returns the featured-game payload with probable pitchers', async () => {
    fetchMock.mockResolvedValue(jsonResponse(payload()));
    const { Wrapper } = makeQueryWrapper();
    const { result } = renderHook(() => useFeaturedGame(), { wrapper: Wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.data.game_pk).toBe(823795);
    expect(result.current.data?.data.status).toBe('preview');
    expect(result.current.data?.data.away.probable_pitcher?.full_name).toBe('Adrian Houser');
    expect(result.current.data?.data.home.run_differential).toBe(15);
  });

  it('exposes ApiError.code = "off_day" on the off-day 503 path', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        { error: { code: 'off_day', message: 'No MLB games scheduled today' } },
        503,
      ),
    );
    const { Wrapper } = makeQueryWrapper();
    const { result } = renderHook(() => useFeaturedGame(), { wrapper: Wrapper });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.status).toBe(503);
    expect(result.current.error?.code).toBe('off_day');
  });

  it('exposes ApiError.code = "data_not_yet_available" on upstream-hiccup 503', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        { error: { code: 'data_not_yet_available', message: 'Schedule unavailable' } },
        503,
      ),
    );
    const { Wrapper } = makeQueryWrapper();
    const { result } = renderHook(() => useFeaturedGame(), { wrapper: Wrapper });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.code).toBe('data_not_yet_available');
  });
});
