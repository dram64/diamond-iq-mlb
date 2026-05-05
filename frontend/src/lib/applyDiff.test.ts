import { describe, expect, it } from 'vitest';

import { applyDiff } from './applyDiff';
import type { ApiGame } from '@/types/api';

function baseGame(overrides: Partial<ApiGame> = {}): ApiGame {
  return {
    game_pk: 822909,
    date: '2026-04-27',
    status: 'live',
    detailed_state: 'In Progress',
    away: { id: 133, name: 'Athletics', abbreviation: 'ATH' },
    home: { id: 140, name: 'Texas Rangers', abbreviation: 'TEX' },
    away_score: 3,
    home_score: 0,
    start_time_utc: '2026-04-27T00:05:00Z',
    linescore: { inning: 5, inning_half: 'Top', balls: 1, strikes: 1, outs: 1 },
    ...overrides,
  };
}

describe('applyDiff', () => {
  it('applies a top-level score change without touching other fields', () => {
    const out = applyDiff(baseGame(), {
      away_score: { old: 3, new: 4 },
    });
    expect(out.away_score).toBe(4);
    expect(out.home_score).toBe(0);
    expect(out.linescore?.inning).toBe(5);
    expect(out.status).toBe('live');
  });

  it('applies nested linescore changes and preserves unchanged linescore fields', () => {
    const out = applyDiff(baseGame(), {
      linescore: {
        inning: { old: 5, new: 6 },
        outs: { old: 1, new: 0 },
      },
    });
    expect(out.linescore?.inning).toBe(6);
    expect(out.linescore?.outs).toBe(0);
    // strikes / balls / inning_half not in the diff — preserved
    expect(out.linescore?.balls).toBe(1);
    expect(out.linescore?.strikes).toBe(1);
    expect(out.linescore?.inning_half).toBe('Top');
  });

  it('applies multiple top-level fields and a nested linescore atomically', () => {
    const out = applyDiff(baseGame(), {
      away_score: { old: 3, new: 4 },
      status: { old: 'live', new: 'final' },
      detailed_state: { old: 'In Progress', new: 'Final' },
      linescore: {
        outs: { old: 1, new: 3 },
      },
    });
    expect(out.away_score).toBe(4);
    expect(out.status).toBe('final');
    expect(out.detailed_state).toBe('Final');
    expect(out.linescore?.outs).toBe(3);
  });

  it('does not mutate the input game object', () => {
    const game = baseGame();
    applyDiff(game, { away_score: { old: 3, new: 99 } });
    expect(game.away_score).toBe(3); // input unchanged
  });

  it('handles inning_half value validation (Top/Bottom only)', () => {
    const out = applyDiff(baseGame(), {
      linescore: {
        inning_half: { old: 'Top', new: 'Bottom' },
      },
    });
    expect(out.linescore?.inning_half).toBe('Bottom');
  });
});
