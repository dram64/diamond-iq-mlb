import type { FinalGame, Game, LiveGame, ScheduledGame } from '@/types';

export const GAMES: readonly Game[] = [
  {
    id: 'g1', status: 'live', inning: 7, half: 'bot', outs: 2,
    away: { id: 'KNG', score: 4, hits: 8, errors: 0 },
    home: { id: 'STR', score: 5, hits: 9, errors: 1 },
    bases: { first: true, second: false, third: true },
    count: { balls: 2, strikes: 1 },
    batter: 'M. Arroyo',
    pitcher: 'D. Volkov',
    leverage: 'high',
    wp: 64,
    venue: 'Cascadia Park',
    startTime: '7:05 PM PT',
    featured: true,
  },
  {
    id: 'g2', status: 'live', inning: 5, half: 'top', outs: 1,
    away: { id: 'HRB', score: 2, hits: 5, errors: 0 },
    home: { id: 'MER', score: 2, hits: 6, errors: 0 },
    bases: { first: true, second: true, third: false },
    count: { balls: 1, strikes: 2 },
    batter: 'J. Okafor',
    pitcher: 'R. Pellegrini',
    leverage: 'med',
    wp: 48,
  },
  {
    id: 'g3', status: 'live', inning: 3, half: 'top', outs: 0,
    away: { id: 'MNT', score: 1, hits: 3, errors: 0 },
    home: { id: 'ALD', score: 0, hits: 2, errors: 0 },
    bases: { first: false, second: false, third: false },
    count: { balls: 0, strikes: 0 },
    batter: 'T. Sandoval',
    pitcher: 'K. Haugen',
    leverage: 'low',
    wp: 52,
  },
  {
    id: 'g7', status: 'live', inning: 8, half: 'top', outs: 2,
    away: { id: 'CRS', score: 6, hits: 11, errors: 0 },
    home: { id: 'CED', score: 3, hits: 7, errors: 1 },
    bases: { first: false, second: true, third: false },
    count: { balls: 3, strikes: 2 },
    batter: 'P. Lindqvist',
    pitcher: 'H. Abara',
    leverage: 'med',
    wp: 18,
  },
  {
    id: 'g8', status: 'live', inning: 6, half: 'bot', outs: 1,
    away: { id: 'NVL', score: 2, hits: 5, errors: 0 },
    home: { id: 'OAK', score: 5, hits: 10, errors: 0 },
    bases: { first: true, second: false, third: false },
    count: { balls: 0, strikes: 1 },
    batter: 'M. Bellisario',
    pitcher: 'K. Tolentino',
    leverage: 'low',
    wp: 82,
  },
  {
    id: 'g9', status: 'live', inning: 4, half: 'top', outs: 0,
    away: { id: 'SHL', score: 3, hits: 4, errors: 0 },
    home: { id: 'RVR', score: 3, hits: 5, errors: 0 },
    bases: { first: false, second: false, third: true },
    count: { balls: 1, strikes: 0 },
    batter: 'E. Caruana',
    pitcher: 'M. Solis',
    leverage: 'high',
    wp: 51,
  },
  {
    id: 'g10', status: 'live', inning: 2, half: 'bot', outs: 2,
    away: { id: 'HRB', score: 0, hits: 1, errors: 0 },
    home: { id: 'KNG', score: 1, hits: 2, errors: 0 },
    bases: { first: false, second: false, third: false },
    count: { balls: 1, strikes: 2 },
    batter: 'S. Moretti',
    pitcher: 'R. Nakashima',
    leverage: 'med',
    wp: 58,
  },
  {
    id: 'g11', status: 'live', inning: 9, half: 'bot', outs: 1,
    away: { id: 'MER', score: 4, hits: 8, errors: 1 },
    home: { id: 'MNT', score: 3, hits: 7, errors: 0 },
    bases: { first: true, second: true, third: false },
    count: { balls: 2, strikes: 2 },
    batter: 'T. Sandoval',
    pitcher: 'R. Pellegrini',
    leverage: 'high',
    wp: 42,
  },
  {
    id: 'g4', status: 'final', inning: 9,
    away: { id: 'OAK', score: 3 },
    home: { id: 'RVR', score: 7 },
  },
  {
    id: 'g5', status: 'final', inning: 10,
    away: { id: 'CED', score: 5 },
    home: { id: 'CRS', score: 4 },
    note: 'F/10',
  },
  {
    id: 'g6', status: 'scheduled', startTime: '7:10 PM ET',
    away: { id: 'NVL' },
    home: { id: 'SHL' },
    prob: { away: 'L. Whitfield (8-6, 3.42)', home: 'E. Caruana (11-4, 2.88)' },
  },
];

/** Extra synthesized finals so the "Final Scores" row has 5 cards on the home page. */
export const EXTRA_FINALS: readonly FinalGame[] = [
  { id: 'f1', status: 'final', inning: 9, away: { id: 'MER', score: 2 }, home: { id: 'ALD', score: 6 } },
  { id: 'f2', status: 'final', inning: 9, away: { id: 'STR', score: 8 }, home: { id: 'SHL', score: 3 } },
  { id: 'f3', status: 'final', inning: 11, away: { id: 'HRB', score: 4 }, home: { id: 'NVL', score: 5 }, note: 'F/11' },
];

export const liveGames = (): readonly LiveGame[] =>
  GAMES.filter((g): g is LiveGame => g.status === 'live');

export const finalGames = (): readonly FinalGame[] =>
  GAMES.filter((g): g is FinalGame => g.status === 'final');

export const scheduledGames = (): readonly ScheduledGame[] =>
  GAMES.filter((g): g is ScheduledGame => g.status === 'scheduled');

/** Home-team win-probability sparkline data keyed by game id. */
export const WP_TRENDS: Readonly<Record<string, readonly number[]>> = {
  g1:  [50, 48, 52, 55, 51, 46, 44, 50, 54, 58, 62, 60, 64],
  g2:  [50, 52, 51, 49, 47, 46, 48, 50, 49, 48],
  g3:  [50, 51, 49, 48, 50, 52],
  g7:  [50, 45, 40, 35, 30, 25, 22, 20, 18],
  g8:  [50, 55, 60, 65, 70, 75, 80, 82],
  g9:  [50, 52, 48, 50, 52, 51],
  g10: [50, 52, 55, 58],
  g11: [50, 55, 52, 48, 45, 50, 48, 45, 42],
};
