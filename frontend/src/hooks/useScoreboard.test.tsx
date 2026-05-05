import { renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useScoreboard } from './useScoreboard';
import { makeQueryWrapper } from '@/test/queryWrapper';
import type { ApiGame, ApiGameStatus, ScoreboardResponse } from '@/types/api';

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
}

function makeGame(overrides: Partial<ApiGame> = {}): ApiGame {
  return {
    game_pk: 1,
    date: '2026-04-25',
    status: 'live',
    detailed_state: 'In Progress',
    away: { id: 133, name: 'Athletics', abbreviation: 'ATH' },
    home: { id: 140, name: 'Texas Rangers', abbreviation: 'TEX' },
    away_score: 0,
    home_score: 0,
    start_time_utc: '2026-04-25T00:05:00Z',
    ...overrides,
  };
}

function scoreboard(date: string, games: ApiGame[]): ScoreboardResponse {
  return { date, count: games.length, games };
}

describe('useScoreboard', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('merges games from both UTC dates and categorizes by status', async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url.includes('?date=')) {
        // Yesterday or today — return distinct payloads
        if (url.includes(new URL(url, 'http://x').searchParams.get('date') ?? '')) {
          // First call returns yesterday's
        }
      }
      // Two URLs differ by date param; identify by URL
      if (fetchMock.mock.calls.length === 1) {
        // First call (yesterday)
        return Promise.resolve(
          jsonResponse(
            scoreboard('y', [
              makeGame({ game_pk: 1, status: 'final' as ApiGameStatus }),
              makeGame({ game_pk: 2, status: 'live' as ApiGameStatus }),
            ]),
          ),
        );
      }
      return Promise.resolve(
        jsonResponse(
          scoreboard('t', [
            makeGame({ game_pk: 3, status: 'live' as ApiGameStatus }),
            makeGame({ game_pk: 4, status: 'preview' as ApiGameStatus }),
            makeGame({ game_pk: 5, status: 'postponed' as ApiGameStatus }),
            makeGame({ game_pk: 6, status: 'scheduled' as ApiGameStatus }),
          ]),
        ),
      );
    });

    const { Wrapper } = makeQueryWrapper();
    const { result } = renderHook(() => useScoreboard(), { wrapper: Wrapper });

    expect(result.current.isLoading).toBe(true);

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.isError).toBe(false);
    expect(result.current.error).toBeNull();
    expect(result.current.games).toHaveLength(6);
    expect(result.current.liveGames.map((g) => g.id)).toEqual(expect.arrayContaining([2, 3]));
    expect(result.current.finalGames.map((g) => g.id)).toEqual([1]);
    expect(result.current.scheduledGames.map((g) => g.id)).toEqual(
      expect.arrayContaining([4, 6]),
    );
    expect(result.current.postponedGames.map((g) => g.id)).toEqual([5]);
    expect(result.current.lastUpdatedAt).not.toBeNull();
  });

  it('fires two parallel fetches on mount', async () => {
    fetchMock.mockResolvedValue(jsonResponse(scoreboard('x', [])));

    const { Wrapper } = makeQueryWrapper();
    const { result } = renderHook(() => useScoreboard(), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('returns games from the successful date when the other fails (partial success)', async () => {
    let call = 0;
    fetchMock.mockImplementation(() => {
      call += 1;
      if (call === 1) {
        return Promise.resolve(
          new Response(JSON.stringify({ error: { code: 'oops', message: 'upstream' } }), {
            status: 500,
            headers: { 'Content-Type': 'application/json' },
          }),
        );
      }
      return Promise.resolve(
        jsonResponse(scoreboard('today', [makeGame({ game_pk: 99, status: 'live' })])),
      );
    });

    const { Wrapper } = makeQueryWrapper();
    const { result } = renderHook(() => useScoreboard(), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.isError).toBe(false);
    expect(result.current.games).toHaveLength(1);
    expect(result.current.liveGames[0]?.id).toBe(99);
  });

  it('reports isError=true and surfaces the first error when both queries fail', async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ error: { code: 'oops', message: 'upstream' } }), {
        status: 500,
      }),
    );

    const { Wrapper } = makeQueryWrapper();
    const { result } = renderHook(() => useScoreboard(), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));

    expect(result.current.error).not.toBeNull();
    expect(result.current.error?.name).toBe('ApiError');
    expect(result.current.games).toHaveLength(0);
  });

  it('refetch triggers both queries again', async () => {
    fetchMock.mockResolvedValue(jsonResponse(scoreboard('x', [])));

    const { Wrapper } = makeQueryWrapper();
    const { result } = renderHook(() => useScoreboard(), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(fetchMock).toHaveBeenCalledTimes(2);

    result.current.refetch();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(4));
  });
});
