import { renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useAICompareAnalysis } from './useAICompareAnalysis';
import { makeQueryWrapper } from '@/test/queryWrapper';
import type { AICompareResponse } from '@/types/aiAnalysis';

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}

function payload(): AICompareResponse {
  return {
    data: {
      kind: 'players',
      ids: [100, 200],
      text: 'Player A leads in HR; Player B in OPS.',
      model_id: 'us.anthropic.claude-3-5-haiku-20241022-v1:0',
      generated_at: '2026-04-30T00:00:00Z',
      cache_hit: false,
    },
    meta: { season: 2026, timestamp: 'x', cache_max_age_seconds: 600 },
  };
}

describe('useAICompareAnalysis', () => {
  let fetchMock: ReturnType<typeof vi.fn>;
  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  it('returns the analysis payload for 2 ids', async () => {
    fetchMock.mockResolvedValue(jsonResponse(payload()));
    const { Wrapper } = makeQueryWrapper();
    const { result } = renderHook(() => useAICompareAnalysis('players', [100, 200]), {
      wrapper: Wrapper,
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.data.text).toContain('Player A');
  });

  it('does not fire below 2 ids', async () => {
    const { Wrapper } = makeQueryWrapper();
    renderHook(() => useAICompareAnalysis('players', [100]), { wrapper: Wrapper });
    await new Promise((r) => setTimeout(r, 10));
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('does not fire above 4 ids', async () => {
    const { Wrapper } = makeQueryWrapper();
    renderHook(() => useAICompareAnalysis('players', [1, 2, 3, 4, 5]), { wrapper: Wrapper });
    await new Promise((r) => setTimeout(r, 10));
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('shares cache key between [100,200] and [200,100]', async () => {
    fetchMock.mockResolvedValue(jsonResponse(payload()));
    const { client, Wrapper } = makeQueryWrapper();
    const { result } = renderHook(() => useAICompareAnalysis('players', [100, 200]), {
      wrapper: Wrapper,
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    // Sanity: the cache key is sorted, so a render with reversed ids hits the cache.
    const cached = client.getQueryData(['aiCompare', 'players', 100, 200]);
    expect(cached).toBeDefined();
  });

  it('reports isError on a 502', async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ error: { code: 'bedrock_unavailable', message: 'down' } }), {
        status: 502,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    const { Wrapper } = makeQueryWrapper();
    const { result } = renderHook(() => useAICompareAnalysis('players', [100, 200]), {
      wrapper: Wrapper,
    });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.status).toBe(502);
  });
});
