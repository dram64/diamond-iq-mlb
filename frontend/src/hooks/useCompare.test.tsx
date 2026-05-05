import { renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useCompare } from './useCompare';
import { makeQueryWrapper } from '@/test/queryWrapper';
import type { CompareResponse } from '@/types/compare';

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
}

function comparePayload(personIds: number[]): CompareResponse {
  return {
    data: {
      players: personIds.map((id) => ({
        person_id: id,
        metadata: { person_id: id, full_name: `Player ${id}` },
        hitting: null,
        pitching: null,
      })),
    },
    meta: { season: 2026, timestamp: '2026-04-27T00:00:00Z', cache_max_age_seconds: 300 },
  };
}

describe('useCompare', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('returns the compare payload for two ids', async () => {
    fetchMock.mockResolvedValue(jsonResponse(comparePayload([592450, 670541])));
    const { Wrapper } = makeQueryWrapper();
    const { result } = renderHook(() => useCompare([592450, 670541]), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.data.players).toHaveLength(2);
  });

  it('returns the compare payload for four ids', async () => {
    fetchMock.mockResolvedValue(jsonResponse(comparePayload([1, 2, 3, 4])));
    const { Wrapper } = makeQueryWrapper();
    const { result } = renderHook(() => useCompare([1, 2, 3, 4]), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.data.players).toHaveLength(4);
  });

  it('does not fire a fetch when fewer than 2 ids supplied', async () => {
    const { Wrapper } = makeQueryWrapper();
    renderHook(() => useCompare([592450]), { wrapper: Wrapper });
    // Give React Query a tick to skip the disabled query.
    await new Promise((r) => setTimeout(r, 10));
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('does not fire a fetch when more than 4 ids supplied', async () => {
    const { Wrapper } = makeQueryWrapper();
    renderHook(() => useCompare([1, 2, 3, 4, 5]), { wrapper: Wrapper });
    await new Promise((r) => setTimeout(r, 10));
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('reports isError on a 4xx response', async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ error: { code: 'player_not_found', message: 'gone' } }), {
        status: 404,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    const { Wrapper } = makeQueryWrapper();
    const { result } = renderHook(() => useCompare([592450, 99999]), { wrapper: Wrapper });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.status).toBe(404);
  });
});
