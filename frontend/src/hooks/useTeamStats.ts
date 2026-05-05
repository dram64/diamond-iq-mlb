/**
 * useTeamStats — fetch a single team's hitting + pitching season aggregates.
 *
 * Disabled (no fetch fired) when `teamId` is null/undefined so the picker can
 * mount in an unselected state without firing a 400.
 *
 * staleTime is 15 minutes to match the backend's
 * `Cache-Control: max-age=900` for /api/teams/{teamId}/stats.
 */

import { useQuery, type UseQueryResult } from '@tanstack/react-query';

import { ApiError, fetchTeamStats } from '@/lib/api';
import type { TeamStatsResponse } from '@/types/teamStats';

const STALE_TIME_MS = 900_000; // 15 minutes

export function useTeamStats(
  teamId: number | null | undefined,
): UseQueryResult<TeamStatsResponse, ApiError> {
  const enabled = teamId != null && Number.isFinite(teamId);
  return useQuery<TeamStatsResponse, ApiError>({
    queryKey: ['teamStats', teamId] as const,
    queryFn: ({ signal }) => fetchTeamStats(teamId as number, { signal }),
    staleTime: STALE_TIME_MS,
    refetchOnWindowFocus: true,
    enabled,
  });
}
