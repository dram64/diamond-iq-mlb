/**
 * Daily AI-content hook.
 *
 * Fetches /content/today and exposes the three categories the home page
 * needs (recap, previews, featured). The endpoint always returns 200 with
 * empty arrays when content hasn't been generated yet, so the hook's
 * `isEmpty` flag distinguishes "successfully retrieved nothing" from
 * "still loading" — the loading skeleton must not flash the empty state.
 *
 * Cache windows are matched to the backend's Cache-Control: max-age=300.
 */

import { useQuery } from '@tanstack/react-query';

import { adaptContent } from '@/lib/adapters';
import { ApiError, fetchDailyContent } from '@/lib/api';
import type { AppContentItem, AppFeaturedItem } from '@/types/app';

export interface UseDailyContentResult {
  recap: AppContentItem[];
  previews: AppContentItem[];
  featured: AppFeaturedItem[];
  /** Date string from the backend response (yyyy-mm-dd UTC). Undefined while loading. */
  date: string | undefined;
  isLoading: boolean;
  isError: boolean;
  error: ApiError | null;
  /** True only after a successful response with all three categories empty. False while loading. */
  isEmpty: boolean;
  refetch: () => void;
}

const STALE_TIME_MS = 5 * 60 * 1000;
const REFETCH_INTERVAL_MS = 5 * 60 * 1000;

export function useDailyContent(): UseDailyContentResult {
  const query = useQuery({
    queryKey: ['daily-content'] as const,
    queryFn: ({ signal }: { signal: AbortSignal }) =>
      fetchDailyContent(undefined, { signal }).then(adaptContent),
    staleTime: STALE_TIME_MS,
    refetchInterval: REFETCH_INTERVAL_MS,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: true,
  });

  const data = query.data;
  const isEmpty =
    !!data && data.recap.length === 0 && data.previews.length === 0 && data.featured.length === 0;

  return {
    recap: data?.recap ?? [],
    previews: data?.previews ?? [],
    featured: data?.featured ?? [],
    date: data?.date,
    isLoading: query.isLoading,
    isError: query.isError,
    error: (query.error as ApiError | null) ?? null,
    isEmpty,
    refetch: () => {
      void query.refetch();
    },
  };
}
