/**
 * useRoster — fetch a team's active roster.
 *
 * staleTime is 6 hours; rosters change rarely intra-day. Disabled when
 * teamId is null/undefined so the hook can mount with a TBD selection.
 */

import { useQuery, type UseQueryResult } from '@tanstack/react-query';

import { ApiError, fetchRoster } from '@/lib/api';

const STALE_TIME_MS = 21_600_000; // 6 hours

export interface RosterEntry {
  person_id: number;
  full_name: string;
  position_abbr: string;
  jersey_number?: string | null;
  status_code?: string | null;
}

export interface RosterData {
  team_id: number;
  roster: RosterEntry[];
}

interface RosterResponseShape {
  data: RosterData;
  meta: { season: number; timestamp: string; cache_max_age_seconds: number };
}

export function useRoster(
  teamId: number | null | undefined,
): UseQueryResult<RosterResponseShape, ApiError> {
  const enabled = teamId != null && Number.isFinite(teamId);
  return useQuery<RosterResponseShape, ApiError>({
    queryKey: ['roster', teamId] as const,
    queryFn: ({ signal }) => fetchRoster(teamId as number, { signal }),
    staleTime: STALE_TIME_MS,
    refetchOnWindowFocus: false,
    enabled,
  });
}
