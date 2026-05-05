import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ReactElement } from 'react';

import { StandingsCard } from './StandingsCard';
import { makeQueryWrapper } from '@/test/queryWrapper';

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
}

function team(id: number, divId: number, divRank: number, runDiff: number) {
  return {
    team_id: id,
    team_name: `Team ${id}`,
    division_id: divId,
    league_id: divId < 203 ? 103 : 104,
    wins: 18 - divRank,
    losses: 10 + divRank,
    pct: '.500',
    games_back: divRank === 1 ? '-' : `${divRank - 1}.0`,
    streak_code: 'W1',
    last_ten_record: '5-5',
    run_differential: runDiff,
    division_rank: String(divRank),
    league_rank: '1',
  };
}

function payload() {
  // Mix two divisions; component must filter to AL West (200) only.
  return {
    data: {
      season: 2026,
      teams: [
        team(100, 201, 1, 30), // AL East — should NOT appear
        team(117, 200, 1, 50), // AL West — Astros
        team(108, 200, 2, 20), // AL West — Angels
        team(136, 200, 3, 10), // AL West — Mariners
        team(140, 200, 4, -5), // AL West — Rangers
        team(133, 200, 5, -20), // AL West — Athletics
      ],
    },
    meta: { season: 2026, timestamp: 'x', cache_max_age_seconds: 900 },
  };
}

function renderInWrapper(ui: ReactElement) {
  const { Wrapper } = makeQueryWrapper();
  return render(<MemoryRouter><Wrapper>{ui}</Wrapper></MemoryRouter>);
}

describe('StandingsCard', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders only teams whose division_id matches the prop', async () => {
    fetchMock.mockResolvedValue(jsonResponse(payload()));
    renderInWrapper(<StandingsCard divisionId={200} />);
    // Wait for the data to arrive (Houston is unique in MLB and only appears
    // when the AL West row for team_id=117 has rendered).
    await waitFor(() => expect(screen.getByText('Houston')).toBeInTheDocument());
    expect(screen.getByText('Seattle')).toBeInTheDocument();
    expect(screen.getByText('Texas')).toBeInTheDocument();
    // Two MLB teams share "Los Angeles" (LAA + LAD); use getAllByText.
    expect(screen.getAllByText('Los Angeles').length).toBeGreaterThanOrEqual(1);
    // The AL East seed (Team 100, id=100, no MLB metadata) should NOT appear.
    expect(screen.queryByText('Team 100')).toBeNull();
  });

  it('uses the division abbr in the default title', () => {
    fetchMock.mockReturnValue(new Promise(() => {}));
    renderInWrapper(<StandingsCard divisionId={200} />);
    expect(screen.getByText(/Standings · AL West/i)).toBeInTheDocument();
  });

  it('honors a custom title prop', () => {
    fetchMock.mockReturnValue(new Promise(() => {}));
    renderInWrapper(<StandingsCard divisionId={200} title="My custom title" />);
    expect(screen.getByText('My custom title')).toBeInTheDocument();
  });

  it('renders teams ordered by division_rank ascending', async () => {
    fetchMock.mockResolvedValue(jsonResponse(payload()));
    renderInWrapper(<StandingsCard divisionId={200} />);
    await waitFor(() => expect(screen.getByText('Houston')).toBeInTheDocument());
    // The component renders rank as the first column. We look for the 5
    // div-rank cells in document order and confirm they're 1..5.
    const ranks = Array.from(document.querySelectorAll('.mono')).map((el) => el.textContent?.trim());
    // First-column rank labels appear as "1", "2", "3", "4", "5" alongside
    // record / GB / run-diff cells. Filtering to single-digit-only entries
    // gives us the rank column.
    const rankOnly = ranks.filter((t) => t && /^[1-5]$/.test(t));
    expect(rankOnly.slice(0, 5)).toEqual(['1', '2', '3', '4', '5']);
  });
});
