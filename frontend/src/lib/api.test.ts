import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError, fetchGame, fetchScoreboard } from './api';
import { API_URL } from './env';

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
}

function errorResponse(status: number, body: unknown = { error: { code: 'oops', message: 'oops' } }): Response {
  return new Response(JSON.stringify(body), {
    status,
    statusText: status === 404 ? 'Not Found' : 'Server Error',
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('fetchScoreboard', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('returns the parsed body on a 200 response', async () => {
    const payload = { date: '2026-04-25', count: 0, games: [] };
    fetchMock.mockResolvedValueOnce(jsonResponse(payload));

    const result = await fetchScoreboard();

    expect(result).toEqual(payload);
  });

  it('builds the URL without a date param when none is given', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ date: '2026-04-25', count: 0, games: [] }));

    await fetchScoreboard();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const calledUrl = fetchMock.mock.calls[0]?.[0] as string;
    expect(calledUrl).toBe(`${API_URL}/scoreboard/today`);
  });

  it('appends an encoded date param when provided', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ date: '2026-04-24', count: 0, games: [] }));

    await fetchScoreboard('2026-04-24');

    const calledUrl = fetchMock.mock.calls[0]?.[0] as string;
    expect(calledUrl).toBe(`${API_URL}/scoreboard/today?date=2026-04-24`);
  });

  it('throws ApiError with status 404 on a 404 response', async () => {
    fetchMock.mockResolvedValueOnce(errorResponse(404, { error: { code: 'not_found', message: 'no such date' } }));

    await expect(fetchScoreboard('2030-01-01')).rejects.toMatchObject({
      name: 'ApiError',
      status: 404,
      message: 'no such date',
    });
  });

  it('throws ApiError with status 500 on a server error', async () => {
    fetchMock.mockResolvedValueOnce(errorResponse(500, { error: { code: 'oops', message: 'boom' } }));

    await expect(fetchScoreboard()).rejects.toMatchObject({
      name: 'ApiError',
      status: 500,
    });
  });

  it('throws ApiError with status 0 on a network failure', async () => {
    fetchMock.mockRejectedValueOnce(new TypeError('failed to fetch'));

    const err = await fetchScoreboard().catch((e: unknown) => e);

    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(0);
    expect((err as ApiError).message).toContain('Network error');
  });

  it('throws ApiError with status 0 on timeout', async () => {
    const timeoutErr = new DOMException('The operation was aborted due to timeout', 'TimeoutError');
    fetchMock.mockRejectedValueOnce(timeoutErr);

    const err = await fetchScoreboard().catch((e: unknown) => e);

    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(0);
    expect((err as ApiError).message).toContain('timed out');
  });

  it('keeps the HTTP statusText when the error body is not JSON', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response('<html>upstream broke</html>', {
        status: 502,
        statusText: 'Bad Gateway',
        headers: { 'Content-Type': 'text/html' },
      }),
    );

    const err = await fetchScoreboard().catch((e: unknown) => e);

    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(502);
    expect((err as ApiError).message).toContain('502');
  });
});

describe('fetchGame', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('builds the right URL with both gameId and date', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        game: {
          game_pk: 822909,
          date: '2026-04-25',
          status: 'live',
          detailed_state: 'In Progress',
          away: { id: 133, name: 'Athletics', abbreviation: 'ATH' },
          home: { id: 140, name: 'Texas Rangers', abbreviation: 'TEX' },
          away_score: 3,
          home_score: 0,
          start_time_utc: '2026-04-25T00:05:00Z',
        },
      }),
    );

    await fetchGame(822909, '2026-04-25');

    const calledUrl = fetchMock.mock.calls[0]?.[0] as string;
    expect(calledUrl).toBe(`${API_URL}/games/822909?date=2026-04-25`);
  });

  it('throws ApiError 404 when the game is missing', async () => {
    fetchMock.mockResolvedValueOnce(errorResponse(404, { error: { code: 'game_not_found', message: 'no game' } }));

    await expect(fetchGame(99999, '2026-04-25')).rejects.toMatchObject({
      name: 'ApiError',
      status: 404,
    });
  });
});
