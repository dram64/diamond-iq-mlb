import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ReactElement } from 'react';

import { HardestHitChart } from './HardestHitChart';
import { makeQueryWrapper } from '@/test/queryWrapper';
import type { HardestHitResponse } from '@/types/hardestHit';

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
}

function payload(): HardestHitResponse {
  return {
    data: {
      date: '2026-04-26',
      limit: 3,
      hits: [
        {
          game_pk: 1001,
          batter_id: 592450,
          batter_name: 'Aaron Judge',
          inning: 5,
          half_inning: 'bottom',
          result_event: 'Home Run',
          launch_speed: 117.8,
          launch_angle: 28,
          total_distance: 425,
          trajectory: 'fly_ball',
        },
        {
          game_pk: 1002,
          batter_id: 670541,
          batter_name: 'Yordan Alvarez',
          inning: 3,
          half_inning: 'top',
          result_event: 'Double',
          launch_speed: 113.4,
          launch_angle: 18,
          total_distance: 380,
          trajectory: 'line_drive',
        },
        {
          game_pk: 1003,
          batter_id: 545361,
          batter_name: 'Mike Trout',
          inning: 7,
          half_inning: 'top',
          result_event: 'Single',
          launch_speed: 110.1,
          launch_angle: 12,
          total_distance: 320,
          trajectory: 'line_drive',
        },
      ],
    },
    meta: { season: 2026, timestamp: '2026-04-27T00:00:00Z', cache_max_age_seconds: 3600 },
  };
}

function renderInWrapper(ui: ReactElement) {
  const { Wrapper } = makeQueryWrapper();
  return render(<Wrapper>{ui}</Wrapper>);
}

describe('HardestHitChart', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders skeleton during initial load', () => {
    fetchMock.mockReturnValue(new Promise(() => {}));
    renderInWrapper(<HardestHitChart date="2026-04-26" />);
    // Real batter names should not appear yet.
    expect(screen.queryByText('Aaron Judge')).toBeNull();
    // Header still renders.
    expect(screen.getByText('Hitter')).toBeInTheDocument();
  });

  it('renders the ranked hits on success with formatted MPH values', async () => {
    fetchMock.mockResolvedValue(jsonResponse(payload()));
    renderInWrapper(<HardestHitChart date="2026-04-26" />);
    await waitFor(() => expect(screen.getByText('Aaron Judge')).toBeInTheDocument());
    expect(screen.getByText('Yordan Alvarez')).toBeInTheDocument();
    expect(screen.getByText('Mike Trout')).toBeInTheDocument();
    // Velocity formatted to 1 decimal.
    expect(screen.getByText('117.8')).toBeInTheDocument();
    expect(screen.getByText('113.4')).toBeInTheDocument();
    // Result events rendered.
    expect(screen.getByText('Home Run')).toBeInTheDocument();
    const judgeImg = screen.getByAltText('Aaron Judge') as HTMLImageElement;
    expect(judgeImg.src).toContain('img.mlbstatic.com');
    expect(judgeImg.src).toContain('/v1/people/592450/headshot/67/current');
  });

  it('renders empty-state on 503 data_not_yet_available without showing a retry button', async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          error: {
            code: 'data_not_yet_available',
            message: 'Hardest-hit ingestion has no data for 2026-04-26',
            details: { date: '2026-04-26' },
          },
        }),
        { status: 503, headers: { 'Content-Type': 'application/json' } },
      ),
    );
    renderInWrapper(<HardestHitChart date="2026-04-26" />);
    await waitFor(() =>
      expect(screen.getByText(/no hardest-hit data for 2026-04-26 yet/i)).toBeInTheDocument(),
    );
    // 503 is a graceful empty state, not a retry-prone failure.
    expect(screen.queryByRole('button', { name: /retry/i })).toBeNull();
  });

  it('renders error state with retry on a non-503 failure', async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ error: { code: 'oops', message: 'down' } }), {
        status: 500,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    renderInWrapper(<HardestHitChart date="2026-04-26" />);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole('button', { name: /retry/i }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  });

  it('renders empty-state when the hits array is empty', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        data: { date: '2026-04-26', limit: 8, hits: [] },
        meta: { season: 2026, timestamp: 'x', cache_max_age_seconds: 3600 },
      }),
    );
    renderInWrapper(<HardestHitChart date="2026-04-26" />);
    await waitFor(() =>
      expect(screen.getByText(/no hardest-hit data for 2026-04-26 yet/i)).toBeInTheDocument(),
    );
  });
});
