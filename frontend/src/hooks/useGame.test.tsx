import { renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useGame } from './useGame';
import { makeQueryWrapper } from '@/test/queryWrapper';
import type { ApiGame, GameDetailResponse } from '@/types/api';

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
}

const SAMPLE: ApiGame = {
  game_pk: 822909,
  date: '2026-04-25',
  status: 'live',
  detailed_state: 'In Progress',
  away: { id: 133, name: 'Athletics', abbreviation: 'ATH' },
  home: { id: 140, name: 'Texas Rangers', abbreviation: 'TEX' },
  away_score: 3,
  home_score: 0,
  start_time_utc: '2026-04-25T00:05:00Z',
};

const DETAIL: GameDetailResponse = { game: SAMPLE };

describe('useGame', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('returns the adapted game on success', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(DETAIL));

    const { Wrapper } = makeQueryWrapper();
    const { result } = renderHook(() => useGame(822909, '2026-04-25'), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.game?.id).toBe(822909);
    expect(result.current.game?.away.fullName).toBe('Athletics');
    expect(result.current.game?.home.fullName).toBe('Texas Rangers');
    expect(result.current.isError).toBe(false);
    expect(result.current.lastUpdatedAt).not.toBeNull();
  });

  it('reports isError=true on a 404', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ error: { code: 'game_not_found', message: 'no game' } }), {
        status: 404,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    const { Wrapper } = makeQueryWrapper();
    const { result } = renderHook(() => useGame(99999, '2026-04-25'), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));

    expect(result.current.game).toBeUndefined();
    expect(result.current.error?.status).toBe(404);
  });

  it('does not fetch when gameId is undefined', async () => {
    fetchMock.mockResolvedValue(jsonResponse(DETAIL));

    const { Wrapper } = makeQueryWrapper();
    renderHook(() => useGame(undefined, '2026-04-25'), { wrapper: Wrapper });

    // Give react-query a tick to do anything it might do
    await new Promise((resolve) => setTimeout(resolve, 20));

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('does not fetch when date is undefined', async () => {
    fetchMock.mockResolvedValue(jsonResponse(DETAIL));

    const { Wrapper } = makeQueryWrapper();
    renderHook(() => useGame(822909, undefined), { wrapper: Wrapper });

    await new Promise((resolve) => setTimeout(resolve, 20));

    expect(fetchMock).not.toHaveBeenCalled();
  });
});
