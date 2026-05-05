import { describe, expect, it } from 'vitest';

import { apiGameToGame, apiScoreboardToGames, apiTeamToTeam, mergeScoreboards } from './adapters';
import type { ApiGame, ApiTeam, ScoreboardResponse } from '@/types/api';

const KNOWN_AWAY: ApiTeam = { id: 133, name: 'Athletics', abbreviation: 'ATH' };
const KNOWN_HOME: ApiTeam = { id: 140, name: 'Texas Rangers', abbreviation: 'TEX' };

function makeApiGame(overrides: Partial<ApiGame> = {}): ApiGame {
  return {
    game_pk: 822909,
    date: '2026-04-25',
    status: 'live',
    detailed_state: 'In Progress',
    away: KNOWN_AWAY,
    home: KNOWN_HOME,
    away_score: 3,
    home_score: 0,
    venue: 'Globe Life Field',
    start_time_utc: '2026-04-25T00:05:00Z',
    linescore: {
      inning: 3,
      inning_half: 'Bottom',
      balls: 3,
      strikes: 1,
      outs: 2,
      away_runs: 3,
      home_runs: 0,
    },
    ...overrides,
  };
}

describe('apiTeamToTeam', () => {
  it('uses the MLB table for known team ids', () => {
    const team = apiTeamToTeam(KNOWN_HOME);
    expect(team.fullName).toBe('Texas Rangers');
    expect(team.locationName).toBe('Texas');
    expect(team.teamName).toBe('Rangers');
    expect(team.primaryColor).toBe('#003278');
    expect(team.secondaryColor).toBe('#C0111F');
  });

  it('falls back to API-supplied data for unknown team ids', () => {
    const team = apiTeamToTeam({ id: 999_999, name: 'Mystery Squad', abbreviation: 'MSQ' });
    expect(team.id).toBe(999_999);
    expect(team.abbreviation).toBe('MSQ');
    expect(team.fullName).toBe('Mystery Squad');
    expect(team.locationName).toBe('');
    expect(team.primaryColor).toBe('');
    expect(team.secondaryColor).toBe('');
  });
});

describe('apiGameToGame', () => {
  it('produces the correct internal Game shape', () => {
    const game = apiGameToGame(makeApiGame());

    expect(game.id).toBe(822909);
    expect(game.date).toBe('2026-04-25');
    expect(game.status).toBe('live');
    expect(game.detailedState).toBe('In Progress');
    expect(game.awayScore).toBe(3);
    expect(game.homeScore).toBe(0);
    expect(game.venue).toBe('Globe Life Field');
    expect(game.startTimeUtc).toBe('2026-04-25T00:05:00Z');
  });

  it('looks up team colors via the MLB table', () => {
    const game = apiGameToGame(makeApiGame());
    expect(game.away.primaryColor).toBe('#003831'); // Athletics green
    expect(game.home.primaryColor).toBe('#003278'); // Rangers blue
  });

  it('leaves bases / batter / pitcher / win probability undefined', () => {
    const game = apiGameToGame(makeApiGame());
    expect(game.bases).toBeUndefined();
    expect(game.batter).toBeUndefined();
    expect(game.pitcher).toBeUndefined();
    expect(game.winProbability).toBeUndefined();
  });

  it('translates inning_half "Top"/"Bottom" to "top"/"bot"', () => {
    const top = apiGameToGame(
      makeApiGame({
        linescore: { inning: 1, inning_half: 'Top', outs: 0, away_runs: 0, home_runs: 0 },
      }),
    );
    expect(top.linescore?.inningHalf).toBe('top');

    const bot = apiGameToGame(
      makeApiGame({
        linescore: { inning: 1, inning_half: 'Bottom', outs: 0, away_runs: 0, home_runs: 0 },
      }),
    );
    expect(bot.linescore?.inningHalf).toBe('bot');
  });

  it('omits linescore when API does not supply it', () => {
    const game = apiGameToGame(makeApiGame({ linescore: undefined }));
    expect(game.linescore).toBeUndefined();
  });

  it('passes all 5 status values through unchanged', () => {
    const statuses = ['live', 'final', 'scheduled', 'preview', 'postponed'] as const;
    for (const status of statuses) {
      const game = apiGameToGame(makeApiGame({ status }));
      expect(game.status).toBe(status);
    }
  });

  it('treats a null venue as undefined', () => {
    const game = apiGameToGame(makeApiGame({ venue: null }));
    expect(game.venue).toBeUndefined();
  });
});

describe('apiScoreboardToGames', () => {
  it('maps each game in the response', () => {
    const response: ScoreboardResponse = {
      date: '2026-04-25',
      count: 2,
      games: [makeApiGame({ game_pk: 1 }), makeApiGame({ game_pk: 2 })],
    };
    expect(apiScoreboardToGames(response).map((g) => g.id)).toEqual([1, 2]);
  });
});

describe('mergeScoreboards', () => {
  function response(date: string, games: ApiGame[]): ScoreboardResponse {
    return { date, count: games.length, games };
  }

  it('merges games from both responses', () => {
    const yesterday = response('2026-04-24', [
      makeApiGame({ game_pk: 1, start_time_utc: '2026-04-24T22:00:00Z' }),
    ]);
    const today = response('2026-04-25', [
      makeApiGame({ game_pk: 2, start_time_utc: '2026-04-25T00:05:00Z' }),
    ]);

    expect(mergeScoreboards(yesterday, today).map((g) => g.id)).toEqual([1, 2]);
  });

  it('deduplicates by game_pk if a game appears in both responses', () => {
    const dup = makeApiGame({ game_pk: 42 });
    const yesterday = response('2026-04-24', [dup]);
    const today = response('2026-04-25', [dup]);
    expect(mergeScoreboards(yesterday, today)).toHaveLength(1);
  });

  it('sorts results ascending by startTimeUtc', () => {
    const games = [
      makeApiGame({ game_pk: 3, start_time_utc: '2026-04-25T03:00:00Z' }),
      makeApiGame({ game_pk: 1, start_time_utc: '2026-04-24T22:00:00Z' }),
      makeApiGame({ game_pk: 2, start_time_utc: '2026-04-25T00:05:00Z' }),
    ];
    const sorted = mergeScoreboards(response('mixed', games));
    expect(sorted.map((g) => g.id)).toEqual([1, 2, 3]);
  });

  it('returns an empty list for empty inputs', () => {
    expect(mergeScoreboards()).toEqual([]);
    expect(mergeScoreboards(response('today', []))).toEqual([]);
  });
});
