import { renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useHardestHit } from './useHardestHit';
import { makeQueryWrapper } from '@/test/queryWrapper';
import type { HardestHitResponse } from '@/types/hardestHit';

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
}

function payload(date: string, count: number): HardestHitResponse {
  const hits = Array.from({ length: count }, (_, i) => ({
    game_pk: 1000 + i,
    batter_id: 500 + i,
    batter_name: `Hitter ${i}`,
    inning: 1 + i,
    half_inning: i % 2 === 0 ? 'top' : 'bottom',
    result_event: 'Single',
    launch_speed: 115 - i * 0.5,
    launch_angle: 25,
    total_distance: 350 - i * 5,
    trajectory: 'line_drive',
  }));
  return {
    data: { date, limit: count, hits },
    meta: { season: 2026, timestamp: '2026-04-27T00:00:00Z', cache_max_age_seconds: 3600 },
  };
}

describe('useHardestHit', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('returns the hardest-hit payload on success', async () => {
    fetchMock.mockResolvedValue(jsonResponse(payload('2026-04-26', 5)));
    const { Wrapper } = makeQueryWrapper();
    const { result } = renderHook(() => useHardestHit('2026-04-26'), { wrapper: Wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.data.hits).toHaveLength(5);
    expect(result.current.data?.data.hits[0].batter_name).toBe('Hitter 0');
  });

  it('reports isLoading=true on initial mount', () => {
    fetchMock.mockReturnValue(new Promise(() => {}));
    const { Wrapper } = makeQueryWrapper();
    const { result } = renderHook(() => useHardestHit('2026-04-26'), { wrapper: Wrapper });
    expect(result.current.isLoading).toBe(true);
  });

  it('surfaces a 503 data_not_yet_available as isError with status 503', async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          error: {
            code: 'data_not_yet_available',
            message: 'Hardest-hit ingestion has no data for 2026-04-26',
            details: { date: '2026-04-26' },
          },
        }),
        { status: 503, headers: { 'Content-Type': 'application/json' } },
      ),
    );
    const { Wrapper } = makeQueryWrapper();
    const { result } = renderHook(() => useHardestHit('2026-04-26'), { wrapper: Wrapper });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.status).toBe(503);
  });

  it('hits the correct API path including date and limit', async () => {
    fetchMock.mockResolvedValue(jsonResponse(payload('2026-04-26', 0)));
    const { Wrapper } = makeQueryWrapper();
    renderHook(() => useHardestHit('2026-04-26', 8), { wrapper: Wrapper });
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const url = fetchMock.mock.calls[0][0] as string;
    expect(url).toContain('/api/hardest-hit/2026-04-26');
    expect(url).toContain('limit=8');
  });

  it('caches by (date, limit) — different dates trigger separate fetches', async () => {
    fetchMock.mockResolvedValue(jsonResponse(payload('2026-04-26', 0)));
    const { Wrapper } = makeQueryWrapper();
    const { rerender } = renderHook(({ date }: { date: string }) => useHardestHit(date), {
      wrapper: Wrapper,
      initialProps: { date: '2026-04-26' },
    });
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    rerender({ date: '2026-04-25' });
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  });
});
