import { renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useDailyContent } from './useDailyContent';
import { makeQueryWrapper } from '@/test/queryWrapper';
import type { ApiContentResponse } from '@/types/api';

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
}

const EMPTY_RESPONSE: ApiContentResponse = {
  date: '2026-04-26',
  recap: [],
  previews: [],
  featured: [],
};

const SEEDED_RESPONSE: ApiContentResponse = {
  date: '2026-04-26',
  recap: [
    {
      text: 'Recap one paragraph.',
      content_type: 'RECAP',
      model_id: 'us.anthropic.claude-sonnet-4-6',
      generated_at_utc: '2026-04-26T15:00:00+00:00',
      game_pk: 1001,
    },
  ],
  previews: [],
  featured: [
    {
      text: 'Featured paragraph.',
      content_type: 'FEATURED',
      model_id: 'us.anthropic.claude-sonnet-4-6',
      generated_at_utc: '2026-04-26T15:00:00+00:00',
      game_pk: 3001,
      rank: 1,
    },
  ],
};

describe('useDailyContent', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('returns isLoading=true on first mount and isEmpty=false', () => {
    fetchMock.mockImplementation(
      () => new Promise(() => {}), // never resolves
    );
    const { Wrapper } = makeQueryWrapper();
    const { result } = renderHook(() => useDailyContent(), { wrapper: Wrapper });
    expect(result.current.isLoading).toBe(true);
    // Loading must NOT mark the data as empty — that would flash the empty state.
    expect(result.current.isEmpty).toBe(false);
  });

  it('marks isEmpty=true after a successful response with three empty arrays', async () => {
    fetchMock.mockResolvedValue(jsonResponse(EMPTY_RESPONSE));
    const { Wrapper } = makeQueryWrapper();
    const { result } = renderHook(() => useDailyContent(), { wrapper: Wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.isEmpty).toBe(true);
    expect(result.current.recap).toEqual([]);
    expect(result.current.featured).toEqual([]);
    expect(result.current.date).toBe('2026-04-26');
  });

  it('returns categorized adapted items on a successful seeded response', async () => {
    fetchMock.mockResolvedValue(jsonResponse(SEEDED_RESPONSE));
    const { Wrapper } = makeQueryWrapper();
    const { result } = renderHook(() => useDailyContent(), { wrapper: Wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.isEmpty).toBe(false);
    expect(result.current.recap).toHaveLength(1);
    expect(result.current.recap[0]?.gamePk).toBe(1001);
    expect(result.current.recap[0]?.contentType).toBe('RECAP');
    expect(result.current.featured).toHaveLength(1);
    expect(result.current.featured[0]?.rank).toBe(1);
    expect(result.current.featured[0]?.gamePk).toBe(3001);
  });

  it('marks isError when the API returns a non-2xx response', async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ error: { code: 'x', message: 'down' } }), { status: 500 }),
    );
    const { Wrapper } = makeQueryWrapper();
    const { result } = renderHook(() => useDailyContent(), { wrapper: Wrapper });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error).not.toBeNull();
  });
});
