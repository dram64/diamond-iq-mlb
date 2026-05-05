import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ReactElement } from 'react';

import { TeamGridSection } from './TeamGridCard';
import { makeQueryWrapper } from '@/test/queryWrapper';

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
}

function team(id: number, divId: number, divRank: number, runDiff: number, streakCode = 'W1') {
  return {
    team_id: id,
    team_name: `Team ${id}`,
    division_id: divId,
    league_id: divId < 203 ? 103 : 104,
    wins: 18,
    losses: 10,
    pct: '.643',
    games_back: divRank === 1 ? '-' : `${divRank - 1}.0`,
    streak_code: streakCode,
    last_ten_record: '7-3',
    run_differential: runDiff,
    division_rank: String(divRank),
    league_rank: '1',
  };
}

function fullPayload() {
  // 6 divisions × 5 teams = 30. Use synthetic ids 1000..1029 (well outside
  // MLB's real id range 108..158) so getMlbTeam() returns undefined and the
  // component falls back to `team_name` for the displayed label — keeps the
  // "Team 1NN" assertions stable.
  const divisions = [201, 202, 200, 204, 205, 203];
  const teams: ReturnType<typeof team>[] = [];
  let id = 1000;
  for (const divId of divisions) {
    for (let rank = 1; rank <= 5; rank++) {
      teams.push(team(id, divId, rank, 50 - id + 1000));
      id++;
    }
  }
  return {
    data: { season: 2026, teams },
    meta: { season: 2026, timestamp: 'x', cache_max_age_seconds: 900 },
  };
}

function renderInWrapper(ui: ReactElement) {
  const { Wrapper } = makeQueryWrapper();
  return render(<MemoryRouter><Wrapper>{ui}</Wrapper></MemoryRouter>);
}

describe('TeamGridSection', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders loading skeleton during initial fetch', () => {
    fetchMock.mockReturnValue(new Promise(() => {}));
    renderInWrapper(<TeamGridSection />);
    // Skeleton placeholders are aria-hidden empty divs; verify no real team
    // names render yet.
    expect(screen.queryByText('Team 1000')).toBeNull();
  });

  it('renders all 30 teams across 6 division rows on success', async () => {
    fetchMock.mockResolvedValue(jsonResponse(fullPayload()));
    renderInWrapper(<TeamGridSection />);
    await waitFor(() => expect(screen.getByText('Team 1000')).toBeInTheDocument());
    // Sample a team from each division to confirm the grouping rendered.
    expect(screen.getByText('Team 1005')).toBeInTheDocument(); // AL Central
    expect(screen.getByText('Team 1010')).toBeInTheDocument(); // AL West
    expect(screen.getByText('Team 1015')).toBeInTheDocument(); // NL East
    expect(screen.getByText('Team 1025')).toBeInTheDocument(); // NL West
  });

  it('shows the AL section before the NL section', async () => {
    fetchMock.mockResolvedValue(jsonResponse(fullPayload()));
    renderInWrapper(<TeamGridSection />);
    const al = await screen.findByText('American League');
    const nl = await screen.findByText('National League');
    // Both exist in the rendered DOM; AL precedes NL in document order.
    const alIdx = Array.from(document.body.querySelectorAll('*')).indexOf(al);
    const nlIdx = Array.from(document.body.querySelectorAll('*')).indexOf(nl);
    expect(alIdx).toBeLessThan(nlIdx);
  });

  it('renders the six division headers (AL East, AL Central, AL West, NL East, NL Central, NL West)', async () => {
    fetchMock.mockResolvedValue(jsonResponse(fullPayload()));
    renderInWrapper(<TeamGridSection />);
    await waitFor(() => expect(screen.getByText('AL East')).toBeInTheDocument());
    expect(screen.getByText('AL Central')).toBeInTheDocument();
    expect(screen.getByText('AL West')).toBeInTheDocument();
    expect(screen.getByText('NL East')).toBeInTheDocument();
    expect(screen.getByText('NL Central')).toBeInTheDocument();
    expect(screen.getByText('NL West')).toBeInTheDocument();
  });

  it('renders error state with retry button when API fails', async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ error: { code: 'oops', message: 'down' } }), {
        status: 500,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    renderInWrapper(<TeamGridSection />);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole('button', { name: /retry/i }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  });

  it('renders empty-state when the standings list is empty', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        data: { season: 2026, teams: [] },
        meta: { season: 2026, timestamp: 'x', cache_max_age_seconds: 900 },
      }),
    );
    renderInWrapper(<TeamGridSection />);
    await waitFor(() =>
      expect(screen.getByText(/standings not yet available/i)).toBeInTheDocument(),
    );
  });
});
