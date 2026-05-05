/**
 * useStandings — fetch the season's division standings.
 *
 * staleTime is 15 minutes to match the API's `Cache-Control: max-age=900`.
 * The standings ingest cron runs once daily at 09:15 UTC, so a longer
 * stale window is fine; window-focus refetch picks up the latest snapshot
 * when the user comes back to the tab.
 */

import { useQuery, type UseQueryResult } from '@tanstack/react-query';

import { ApiError, fetchStandings } from '@/lib/api';
import type { StandingsResponse } from '@/types/standings';

const STALE_TIME_MS = 900_000; // 15 minutes

function defaultSeason(): number {
  return new Date().getUTCFullYear();
}

export function useStandings(
  season: number = defaultSeason(),
): UseQueryResult<StandingsResponse, ApiError> {
  return useQuery<StandingsResponse, ApiError>({
    queryKey: ['standings', season] as const,
    queryFn: ({ signal }) => fetchStandings(season, { signal }),
    staleTime: STALE_TIME_MS,
    refetchOnWindowFocus: true,
  });
}
