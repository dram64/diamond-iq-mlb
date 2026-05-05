import { useQuery, type UseQueryResult } from '@tanstack/react-query';

import { ApiError, fetchFeaturedGame } from '@/lib/api';
import type { FeaturedGameResponse } from '@/types/featuredGame';

const STALE_TIME_MS = 180_000; // 3 minutes — matches Cache-Control max-age

export function useFeaturedGame(): UseQueryResult<FeaturedGameResponse, ApiError> {
  return useQuery<FeaturedGameResponse, ApiError>({
    queryKey: ['featuredGame'] as const,
    queryFn: ({ signal }) => fetchFeaturedGame({ signal }),
    staleTime: STALE_TIME_MS,
    refetchOnWindowFocus: true,
    // The route already returns 503 cleanly for the two known
    // miss-paths (off-day, MLB hiccup) — don't retry, surface fast.
    retry: false,
  });
}
