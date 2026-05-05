import { renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useLeaders } from './useLeaders';
import { makeQueryWrapper } from '@/test/queryWrapper';
import type { LeadersResponse } from '@/types/leaders';

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
}

function leadersPayload(
  group: 'hitting' | 'pitching',
  stat: string,
  leaders: Array<{ person_id: number; full_name: string; rank: number }>,
): LeadersResponse {
  return {
    data: {
      group,
      stat,
      field: stat,
      direction: 'desc',
      limit: leaders.length,
      leaders,
    },
    meta: { season: 2026, timestamp: '2026-04-27T00:00:00Z', cache_max_age_seconds: 600 },
  };
}

describe('useLeaders', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('returns leaders payload on a successful fetch', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        leadersPayload('hitting', 'woba', [
          { person_id: 592450, full_name: 'Aaron Judge', rank: 1 },
        ]),
      ),
    );
    const { Wrapper } = makeQueryWrapper();
    const { result } = renderHook(() => useLeaders('hitting', 'woba', 5), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.data.leaders).toHaveLength(1);
    expect(result.current.data?.data.leaders[0].full_name).toBe('Aaron Judge');
  });

  it('reports isLoading=true on initial mount', () => {
    fetchMock.mockReturnValue(new Promise(() => {})); // never resolves
    const { Wrapper } = makeQueryWrapper();
    const { result } = renderHook(() => useLeaders('hitting', 'avg'), { wrapper: Wrapper });
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
    const { result } = renderHook(() => useLeaders('hitting', 'avg'), { wrapper: Wrapper });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.name).toBe('ApiError');
  });

  it('calls the API with the correct path including limit', async () => {
    fetchMock.mockResolvedValue(jsonResponse(leadersPayload('pitching', 'era', [])));
    const { Wrapper } = makeQueryWrapper();
    renderHook(() => useLeaders('pitching', 'era', 7), { wrapper: Wrapper });
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const calledUrl = fetchMock.mock.calls[0][0] as string;
    expect(calledUrl).toContain('/api/leaders/pitching/era');
    expect(calledUrl).toContain('limit=7');
  });

  it('caches by (group, stat, limit) — different limits trigger separate fetches', async () => {
    fetchMock.mockResolvedValue(jsonResponse(leadersPayload('hitting', 'avg', [])));
    const { Wrapper } = makeQueryWrapper();
    const { rerender } = renderHook(({ limit }: { limit: number }) => useLeaders('hitting', 'avg', limit), {
      wrapper: Wrapper,
      initialProps: { limit: 5 },
    });
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    rerender({ limit: 10 });
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  });
});
