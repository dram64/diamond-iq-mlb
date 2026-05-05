/**
 * useLeaders — fetch top-N leaders for a (group, stat) pair.
 *
 * staleTime is 10 minutes to match the API's `Cache-Control: max-age=600`,
 * so React Query won't refetch within the window the backend itself
 * considers fresh. Background refetch on window focus is enabled so a
 * leaderboard reflects fresh data when the user comes back to the tab.
 */

import { useQuery, type UseQueryResult } from '@tanstack/react-query';

import { ApiError, fetchLeaders } from '@/lib/api';
import type { LeaderGroup, LeadersResponse } from '@/types/leaders';

const STALE_TIME_MS = 600_000; // 10 minutes

export function useLeaders(
  group: LeaderGroup,
  stat: string,
  limit = 5,
): UseQueryResult<LeadersResponse, ApiError> {
  return useQuery<LeadersResponse, ApiError>({
    queryKey: ['leaders', group, stat, limit] as const,
    queryFn: ({ signal }) => fetchLeaders(group, stat, limit, { signal }),
    staleTime: STALE_TIME_MS,
    refetchOnWindowFocus: true,
    // retry: 2 with exponential backoff is set on the QueryClient default
    // in main.tsx; tests override via their wrapper.
  });
}
