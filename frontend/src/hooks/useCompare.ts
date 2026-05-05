import { useMemo } from 'react';
import { useQuery, type UseQueryResult } from '@tanstack/react-query';

import { ApiError, fetchCompare } from '@/lib/api';
import type { CompareResponse } from '@/types/compare';

const STALE_TIME_MS = 300_000; // 5 minutes
const MIN_IDS = 2;
const MAX_IDS = 4;

export function useCompare(
  ids: readonly number[],
): UseQueryResult<CompareResponse, ApiError> {
  // Sort the cache key so [592450, 670541] and [670541, 592450] share
  // a single cached entry — order doesn't change the visual result
  // beyond which player renders on the left.
  const sortedIds = useMemo(() => [...ids].sort((a, b) => a - b), [ids]);
  const enabled = sortedIds.length >= MIN_IDS && sortedIds.length <= MAX_IDS;

  return useQuery<CompareResponse, ApiError>({
    queryKey: ['compare', ...sortedIds] as const,
    queryFn: ({ signal }) => fetchCompare(ids, { signal }),
    staleTime: STALE_TIME_MS,
    refetchOnWindowFocus: true,
    enabled,
  });
}
