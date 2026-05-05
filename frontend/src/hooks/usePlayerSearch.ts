import { useQuery, type UseQueryResult } from '@tanstack/react-query';

import { ApiError, fetchPlayerSearch } from '@/lib/api';
import type { PlayerSearchResponse } from '@/types/search';

const STALE_TIME_MS = 60_000;
const MIN_QUERY_LEN = 2;

export function usePlayerSearch(
  query: string,
  limit = 10,
): UseQueryResult<PlayerSearchResponse, ApiError> {
  const trimmed = query.trim();
  const enabled = trimmed.length >= MIN_QUERY_LEN;
  return useQuery<PlayerSearchResponse, ApiError>({
    queryKey: ['playerSearch', trimmed, limit] as const,
    queryFn: ({ signal }) => fetchPlayerSearch(trimmed, limit, { signal }),
    staleTime: STALE_TIME_MS,
    enabled,
    refetchOnWindowFocus: false,
  });
}
