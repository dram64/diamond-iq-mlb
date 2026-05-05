import { renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { usePlayerSearch } from './usePlayerSearch';
import { makeQueryWrapper } from '@/test/queryWrapper';
import type { PlayerSearchResponse } from '@/types/search';

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}

function payload(): PlayerSearchResponse {
  return {
    data: {
      query: 'judge',
      results: [
        { person_id: 592450, full_name: 'Aaron Judge', primary_position_abbr: 'RF', primary_number: '99' },
      ],
      count: 1,
    },
    meta: { season: 2026, timestamp: 'x', cache_max_age_seconds: 60 },
  };
}

describe('usePlayerSearch', () => {
  let fetchMock: ReturnType<typeof vi.fn>;
  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  it('returns matches for a 2+ char query', async () => {
    fetchMock.mockResolvedValue(jsonResponse(payload()));
    const { Wrapper } = makeQueryWrapper();
    const { result } = renderHook(() => usePlayerSearch('judge'), { wrapper: Wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.data.count).toBe(1);
  });

  it('does not fire below 2 characters', async () => {
    const { Wrapper } = makeQueryWrapper();
    renderHook(() => usePlayerSearch('a'), { wrapper: Wrapper });
    await new Promise((r) => setTimeout(r, 10));
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('does not fire on empty query', async () => {
    const { Wrapper } = makeQueryWrapper();
    renderHook(() => usePlayerSearch('   '), { wrapper: Wrapper });
    await new Promise((r) => setTimeout(r, 10));
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('URL-encodes the query', async () => {
    fetchMock.mockResolvedValue(jsonResponse(payload()));
    const { Wrapper } = makeQueryWrapper();
    renderHook(() => usePlayerSearch('aa bb'), { wrapper: Wrapper });
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const url = fetchMock.mock.calls[0][0] as string;
    // encodeURIComponent maps space → %20.
    expect(url).toContain('q=aa%20bb');
  });
});
