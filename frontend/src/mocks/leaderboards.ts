import type {
  BattingLeader,
  HardestHitEntry,
  LeaderboardRow,
  PitchingLeader,
} from '@/types';

export const BATTING_LEADERS: readonly BattingLeader[] = [
  { name: 'M. Arroyo',   team: 'STR', avg: 0.341, hr: 38, rbi: 102, war: 8.2, trend: [5, 6, 7, 6, 7, 8, 7, 8] },
  { name: 'E. Caruana',  team: 'SHL', avg: 0.302, hr: 29, rbi:  94, war: 7.8, trend: [4, 5, 6, 6, 7, 7, 8, 8] },
  { name: 'K. Haugen',   team: 'ALD', avg: 0.314, hr: 34, rbi:  98, war: 7.1, trend: [3, 5, 5, 6, 6, 7, 7, 7] },
  { name: 'N. Park',     team: 'STR', avg: 0.288, hr: 31, rbi:  88, war: 6.4, trend: [5, 4, 5, 6, 5, 6, 6, 7] },
  { name: 'J. Okafor',   team: 'HRB', avg: 0.295, hr: 27, rbi:  81, war: 6.2, trend: [4, 5, 5, 5, 6, 6, 6, 7] },
];

export const PITCHING_LEADERS: readonly PitchingLeader[] = [
  { name: 'C. Madani',     team: 'STR', era: 2.08, wl: '14-3',  k: 214, whip: 0.94, trend: [7, 7, 8, 7, 8, 8, 9, 8] },
  { name: 'E. Caruana',    team: 'SHL', era: 2.21, wl: '11-4',  k: 198, whip: 0.98, trend: [6, 7, 7, 7, 8, 8, 7, 8] },
  { name: 'R. Solberg',    team: 'STR', era: 2.64, wl: '12-5',  k: 186, whip: 1.02, trend: [5, 6, 6, 7, 6, 7, 7, 7] },
  { name: 'D. Volkov',     team: 'KNG', era: 2.84, wl: '10-6',  k: 176, whip: 1.08, trend: [6, 6, 5, 6, 7, 6, 7, 7] },
  { name: 'T. Nakashima',  team: 'MNT', era: 2.91, wl: '12-7',  k: 171, whip: 1.11, trend: [5, 5, 6, 6, 6, 7, 6, 7] },
];

export const HARDEST_HIT: readonly HardestHitEntry[] = [
  { name: 'K. Haugen',    team: 'ALD', mph: 117.8, result: 'Double' },
  { name: 'N. Park',      team: 'STR', mph: 115.4, result: 'HR (31)' },
  { name: 'S. Moretti',   team: 'KNG', mph: 114.2, result: 'Line out' },
  { name: 'M. Arroyo',    team: 'STR', mph: 113.6, result: 'Single' },
  { name: 'J. Okafor',    team: 'HRB', mph: 112.9, result: 'HR (27)' },
  { name: 'A. Tendo',     team: 'RVR', mph: 111.5, result: 'Double' },
  { name: 'C. Rivas',     team: 'STR', mph: 110.8, result: 'Single' },
  { name: 'T. Sandoval',  team: 'MNT', mph: 110.1, result: 'Line out' },
];

export const LEADERBOARD_WAR: readonly LeaderboardRow[] = [
  { rank:  1, name: 'M. Arroyo',     team: 'STR', era: '2026', g: 128, war: 8.2, avg: 0.341, hr: 38, ops: 1.029 },
  { rank:  2, name: 'E. Caruana',    team: 'SHL', era: '2026', g: 130, war: 7.8, avg: 0.302, hr: 29, ops: 0.956 },
  { rank:  3, name: 'K. Haugen',     team: 'ALD', era: '2026', g: 127, war: 7.1, avg: 0.314, hr: 34, ops: 0.981 },
  { rank:  4, name: 'N. Park',       team: 'STR', era: '2026', g: 129, war: 6.4, avg: 0.288, hr: 31, ops: 0.907 },
  { rank:  5, name: 'J. Okafor',     team: 'HRB', era: '2026', g: 126, war: 6.2, avg: 0.295, hr: 27, ops: 0.891 },
  { rank:  6, name: 'R. Pellegrini', team: 'MER', era: '2026', g: 130, war: 5.9, avg: 0.272, hr: 33, ops: 0.878 },
  { rank:  7, name: 'C. Rivas',      team: 'STR', era: '2026', g: 124, war: 5.7, avg: 0.312, hr: 19, ops: 0.884 },
  { rank:  8, name: 'S. Moretti',    team: 'KNG', era: '2026', g: 128, war: 5.5, avg: 0.281, hr: 28, ops: 0.862 },
  { rank:  9, name: 'T. Sandoval',   team: 'MNT', era: '2026', g: 125, war: 5.2, avg: 0.299, hr: 22, ops: 0.851 },
  { rank: 10, name: 'L. Bramwell',   team: 'STR', era: '2026', g: 118, war: 5.0, avg: 0.291, hr: 24, ops: 0.845 },
  { rank: 11, name: 'D. Volkov',     team: 'KNG', era: '2026', g: 121, war: 4.8, avg: 0.276, hr: 26, ops: 0.822 },
  { rank: 12, name: 'A. Tendo',      team: 'RVR', era: '2026', g: 127, war: 4.6, avg: 0.284, hr: 21, ops: 0.814 },
];
