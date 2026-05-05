import type { DivisionStandingsRow, StandingsRow } from '@/types';

export const STANDINGS_HOME: readonly StandingsRow[] = [
  { team: 'STR', rec: '78-52', gb: '—',    rd: '+112', l10: '7-3' },
  { team: 'KNG', rec: '76-54', gb: '2.0',  rd: '+84',  l10: '6-4' },
  { team: 'MNT', rec: '71-59', gb: '7.0',  rd: '+41',  l10: '5-5' },
  { team: 'ALD', rec: '70-60', gb: '8.0',  rd: '+38',  l10: '5-5' },
  { team: 'HRB', rec: '68-62', gb: '10.0', rd: '+12',  l10: '6-4' },
];

export const STANDINGS_PL_WEST: readonly DivisionStandingsRow[] = [
  { team: 'STR', rec: '78-52', pct: 0.600, gb: '—',    l10: '7-3', strk: 'W3' },
  { team: 'KNG', rec: '76-54', pct: 0.585, gb: '2.0',  l10: '6-4', strk: 'L1' },
  { team: 'ALD', rec: '70-60', pct: 0.538, gb: '8.0',  l10: '5-5', strk: 'W1' },
  { team: 'MER', rec: '65-65', pct: 0.500, gb: '13.0', l10: '4-6', strk: 'L2' },
  { team: 'SHL', rec: '52-78', pct: 0.400, gb: '26.0', l10: '3-7', strk: 'L4' },
];
