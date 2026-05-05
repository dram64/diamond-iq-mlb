import { renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useTeamStats } from './useTeamStats';
import { makeQueryWrapper } from '@/test/queryWrapper';
import type { TeamStatsResponse } from '@/types/teamStats';

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
}

function teamPayload(teamId: number): TeamStatsResponse {
  return {
    data: {
      team_id: teamId,
      team_name: `Team ${teamId}`,
      season: 2026,
      hitting: { avg: '.260', home_runs: 50 },
      pitching: { era: '3.50', strikeouts: 280 },
    },
    meta: { season: 2026, timestamp: '2026-04-30T00:00:00Z', cache_max_age_seconds: 900 },
  };
}

describe('useTeamStats', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('returns the team-stats payload for a valid id', async () => {
    fetchMock.mockResolvedValue(jsonResponse(teamPayload(147)));
    const { Wrapper } = makeQueryWrapper();
    const { result } = renderHook(() => useTeamStats(147), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.data.team_name).toBe('Team 147');
    expect(result.current.data?.data.hitting.home_runs).toBe(50);
  });

  it('does not fire a fetch when teamId is null', async () => {
    const { Wrapper } = makeQueryWrapper();
    renderHook(() => useTeamStats(null), { wrapper: Wrapper });
    await new Promise((r) => setTimeout(r, 10));
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('does not fire a fetch when teamId is undefined', async () => {
    const { Wrapper } = makeQueryWrapper();
    renderHook(() => useTeamStats(undefined), { wrapper: Wrapper });
    await new Promise((r) => setTimeout(r, 10));
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('reports isError on a 503 response', async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          error: { code: 'data_not_yet_available', message: 'Not yet ingested' },
        }),
        { status: 503, headers: { 'Content-Type': 'application/json' } },
      ),
    );
    const { Wrapper } = makeQueryWrapper();
    const { result } = renderHook(() => useTeamStats(999), { wrapper: Wrapper });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.status).toBe(503);
  });
});
