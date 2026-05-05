import { renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useTeamCompare } from './useTeamCompare';
import { makeQueryWrapper } from '@/test/queryWrapper';
import type { TeamCompareResponse } from '@/types/teamStats';

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
}

function comparePayload(teamIds: number[]): TeamCompareResponse {
  return {
    data: {
      season: 2026,
      teams: teamIds.map((id) => ({
        team_id: id,
        team_name: `Team ${id}`,
        season: 2026,
        hitting: { avg: '.250', home_runs: 40 + id },
        pitching: { era: '3.80', strikeouts: 250 + id },
      })),
    },
    meta: { season: 2026, timestamp: '2026-04-30T00:00:00Z', cache_max_age_seconds: 900 },
  };
}

describe('useTeamCompare', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('returns the compare payload for two ids', async () => {
    fetchMock.mockResolvedValue(jsonResponse(comparePayload([147, 121])));
    const { Wrapper } = makeQueryWrapper();
    const { result } = renderHook(() => useTeamCompare([147, 121]), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.data.teams).toHaveLength(2);
  });

  it('returns the compare payload for four ids', async () => {
    fetchMock.mockResolvedValue(jsonResponse(comparePayload([147, 121, 117, 119])));
    const { Wrapper } = makeQueryWrapper();
    const { result } = renderHook(() => useTeamCompare([147, 121, 117, 119]), {
      wrapper: Wrapper,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.data.teams).toHaveLength(4);
  });

  it('does not fire a fetch when fewer than 2 ids supplied', async () => {
    const { Wrapper } = makeQueryWrapper();
    renderHook(() => useTeamCompare([147]), { wrapper: Wrapper });
    await new Promise((r) => setTimeout(r, 10));
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('does not fire a fetch when more than 4 ids supplied', async () => {
    const { Wrapper } = makeQueryWrapper();
    renderHook(() => useTeamCompare([1, 2, 3, 4, 5]), { wrapper: Wrapper });
    await new Promise((r) => setTimeout(r, 10));
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('reports isError on a 404 response', async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({ error: { code: 'team_not_found', message: 'gone' } }),
        { status: 404, headers: { 'Content-Type': 'application/json' } },
      ),
    );
    const { Wrapper } = makeQueryWrapper();
    const { result } = renderHook(() => useTeamCompare([147, 99999]), { wrapper: Wrapper });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.status).toBe(404);
  });
});
