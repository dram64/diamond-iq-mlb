import type { LiveGameDetail } from '@/types';

/**
 * Per-gameId detail for the live tracker. Only g1 has real content in the mock;
 * `liveGameDetail()` falls back to g1 for any other live id so the UI renders
 * cleanly. When the backend ships this is the module that gets replaced.
 */
const G1_DETAIL: LiveGameDetail = {
  batterSide: 'L',
  batterDetail: 'CF · .326 / 25 HR',
  pitcherRole: 'Pitcher · RHP',
  pitcherDetail: '2.84 ERA · 11.3 K/9',
  pitcherLine: '6.2 IP · 4 H · 3 ER · 2 BB · 9 K · 92 pitches',

  plays: [
    { inning: 7, half: 'bot', desc: 'M. Arroyo at bat. 2-1 count.', type: 'atbat', live: true },
    { inning: 7, half: 'bot', desc: 'Ball 2, low and away (94.1 mph sinker).', type: 'pitch' },
    { inning: 7, half: 'bot', desc: 'Foul, 1-1. (97.3 mph four-seam, upper third).', type: 'pitch' },
    { inning: 7, half: 'bot', desc: 'Ball 1, high. (96.8 mph four-seam).', type: 'pitch' },
    { inning: 7, half: 'bot', desc: 'C. Rivas singled sharply to right. Arroyo to 3rd.', type: 'hit' },
    { inning: 7, half: 'bot', desc: 'L. Bramwell struck out swinging (slider, low).', type: 'out' },
    { inning: 7, half: 'bot', desc: 'N. Park walked on four pitches.', type: 'walk' },
    { inning: 6, half: 'top', desc: 'Foxes 4, Steelhead 4 → end 6.', type: 'inning' },
    { inning: 6, half: 'top', desc: 'S. Moretti grounded out, 4-3. RBI.', type: 'out' },
    { inning: 6, half: 'top', desc: 'J. Okafor doubled to the gap in left-center.', type: 'hit' },
    { inning: 5, half: 'bot', desc: 'N. Park homered (14) to right-center. 4-3 Steelhead.', type: 'hr' },
  ],

  pitches: [
    { n: 1, type: 'SI', mph: 94.1, x: -0.85, y: 0.18, result: 'ball' },
    { n: 2, type: 'FF', mph: 97.3, x:  0.15, y: 0.82, result: 'foul' },
    { n: 3, type: 'FF', mph: 96.8, x:  0.05, y: 1.05, result: 'ball' },
  ],

  matchup: [
    { label: 'AVG',      batter: '.326',  pitcher: '.214'  },
    { label: 'OBP',      batter: '.401',  pitcher: '.278'  },
    { label: 'SLG',      batter: '.568',  pitcher: '.351'  },
    { label: 'K%',       batter: '17.2%', pitcher: '26.8%' },
    { label: 'BB%',      batter: '11.4%', pitcher: '8.9%'  },
    { label: 'Hard hit', batter: '48.1%', pitcher: '41.2%' },
    { label: 'xwOBA',    batter: '.401',  pitcher: '.298'  },
  ],

  pitchMix: [
    { name: '4-seam', pct: 42, mph: '97.3', whiff: '24%' },
    { name: 'Sinker', pct: 26, mph: '94.8', whiff: '11%' },
    { name: 'Slider', pct: 22, mph: '88.1', whiff: '38%' },
    { name: 'Change', pct: 10, mph: '86.4', whiff: '29%' },
  ],

  analyst: {
    topic: "Volkov's lost the upstairs fastball",
    paragraphs: [
      'Through six, the four-seam was averaging 97.8 with 18 inches of vertical break. This inning: 96.2, 14 inches, and catcher framing on the two he’s thrown up. The elite shape is gone.',
      'Expect the slider here. If it hangs, it’s a run.',
    ],
    byline: 'The Beat',
    ts: 'live · 12s ago',
  },
};

const DETAIL_BY_ID: Readonly<Record<string, LiveGameDetail>> = {
  g1: G1_DETAIL,
};

/** Look up per-game detail; falls back to the featured g1 for any other id. */
export function liveGameDetail(gameId: string): LiveGameDetail {
  return DETAIL_BY_ID[gameId] ?? G1_DETAIL;
}
