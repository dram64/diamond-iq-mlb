import { useMemo } from 'react';
import { useQuery, type UseQueryResult } from '@tanstack/react-query';

import { ApiError, fetchAICompareAnalysis } from '@/lib/api';
import type { AICompareKind, AICompareResponse } from '@/types/aiAnalysis';

const STALE_TIME_MS = 600_000; // 10 minutes
const MIN_IDS = 2;
const MAX_IDS = 4;

export function useAICompareAnalysis(
  kind: AICompareKind,
  ids: readonly number[],
): UseQueryResult<AICompareResponse, ApiError> {
  const sortedIds = useMemo(() => [...ids].sort((a, b) => a - b), [ids]);
  const enabled = sortedIds.length >= MIN_IDS && sortedIds.length <= MAX_IDS;
  return useQuery<AICompareResponse, ApiError>({
    queryKey: ['aiCompare', kind, ...sortedIds] as const,
    queryFn: ({ signal }) => fetchAICompareAnalysis(kind, ids, { signal }),
    staleTime: STALE_TIME_MS,
    enabled,
    refetchOnWindowFocus: false,
    // Bedrock failures are transient; ApiError surfaces 502 as the user
    // visible cue to retry. React Query will not retry on its own — we
    // surface a Retry button instead.
    retry: false,
  });
}
