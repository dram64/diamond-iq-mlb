import { useQuery, type UseQueryResult } from '@tanstack/react-query';

import { ApiError, fetchFeaturedMatchup } from '@/lib/api';
import type { FeaturedMatchupResponse } from '@/types/featuredMatchup';

const STALE_TIME_MS = 3_600_000; // 1 hour

export function useFeaturedMatchup(): UseQueryResult<FeaturedMatchupResponse, ApiError> {
  return useQuery<FeaturedMatchupResponse, ApiError>({
    queryKey: ['featuredMatchup'] as const,
    queryFn: ({ signal }) => fetchFeaturedMatchup({ signal }),
    staleTime: STALE_TIME_MS,
    refetchOnWindowFocus: false,
  });
}
