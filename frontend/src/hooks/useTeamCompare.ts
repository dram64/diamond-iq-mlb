import { useMemo } from 'react';
import { useQuery, type UseQueryResult } from '@tanstack/react-query';

import { ApiError, fetchTeamCompare } from '@/lib/api';
import type { TeamCompareResponse } from '@/types/teamStats';

const STALE_TIME_MS = 900_000; // 15 minutes
const MIN_IDS = 2;
const MAX_IDS = 4;

export function useTeamCompare(
  ids: readonly number[],
): UseQueryResult<TeamCompareResponse, ApiError> {
  // Sort the cache key so [147, 121] and [121, 147] share a single cached
  // entry — order doesn't change the visual result beyond which team renders
  // on the left.
  const sortedIds = useMemo(() => [...ids].sort((a, b) => a - b), [ids]);
  const enabled = sortedIds.length >= MIN_IDS && sortedIds.length <= MAX_IDS;

  return useQuery<TeamCompareResponse, ApiError>({
    queryKey: ['teamCompare', ...sortedIds] as const,
    queryFn: ({ signal }) => fetchTeamCompare(ids, { signal }),
    staleTime: STALE_TIME_MS,
    refetchOnWindowFocus: true,
    enabled,
  });
}
