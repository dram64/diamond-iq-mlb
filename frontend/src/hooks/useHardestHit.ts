import { useQuery, type UseQueryResult } from '@tanstack/react-query';

import { ApiError, fetchHardestHit } from '@/lib/api';
import { yesterdayUtcDate } from '@/lib/dateUtils';
import type { HardestHitResponse } from '@/types/hardestHit';

const STALE_TIME_MS = 3_600_000; // 1 hour

export function useHardestHit(
  date: string = yesterdayUtcDate(),
  limit?: number,
): UseQueryResult<HardestHitResponse, ApiError> {
  return useQuery<HardestHitResponse, ApiError>({
    queryKey: ['hardest-hit', date, limit ?? null] as const,
    queryFn: ({ signal }) => fetchHardestHit(date, limit, { signal }),
    staleTime: STALE_TIME_MS,
    refetchOnWindowFocus: false,
  });
}
