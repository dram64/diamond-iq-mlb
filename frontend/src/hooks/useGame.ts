/**
 * Single-game detail hook for the live game tracker.
 *
 * Polls every 30s when the tab is visible. Disabled until both gameId
 * and date are provided, so the hook is safe to call from a route
 * component before the URL params resolve.
 */

import { useQuery } from '@tanstack/react-query';

import { ApiError, fetchGame } from '@/lib/api';
import { apiGameToGame } from '@/lib/adapters';
import type { AppGame } from '@/types/app';

export interface UseGameResult {
  game: AppGame | undefined;
  isLoading: boolean;
  isError: boolean;
  error: ApiError | null;
  refetch: () => void;
  lastUpdatedAt: number | null;
}

const STALE_TIME_MS = 15_000;
const REFETCH_INTERVAL_MS = 30_000;

export function useGame(gameId: number | undefined, date: string | undefined): UseGameResult {
  const enabled = typeof gameId === 'number' && Number.isFinite(gameId) && !!date;

  const query = useQuery({
    queryKey: ['game', gameId, date] as const,
    queryFn: async ({ signal }) => {
      // Narrowed by `enabled`, but TypeScript doesn't know that — assert.
      if (!enabled) throw new Error('useGame query ran while disabled');
      return fetchGame(gameId as number, date as string, { signal });
    },
    enabled,
    staleTime: STALE_TIME_MS,
    refetchInterval: REFETCH_INTERVAL_MS,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: true,
    // retry: 2 inherited from QueryClient defaults in main.tsx.
  });

  return {
    game: query.data ? apiGameToGame(query.data.game) : undefined,
    isLoading: query.isLoading,
    isError: query.isError,
    error: (query.error as ApiError | null | undefined) ?? null,
    refetch: () => {
      void query.refetch();
    },
    lastUpdatedAt: query.dataUpdatedAt > 0 ? query.dataUpdatedAt : null,
  };
}
