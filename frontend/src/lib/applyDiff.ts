/**
 * Apply a score_update diff payload to a cached ApiGame.
 *
 * The diff payload comes through in wire-shape (snake_case keys), and the
 * cache stores wire-shape values too (the GameDetailResponse type wraps
 * an ApiGame). So this module operates entirely on snake_case fields and
 * is the simplest possible reconciliation: copy the `new` value into the
 * matching field.
 *
 * Pure function. Returns a new ApiGame object — never mutates input.
 */

import type {
  ApiGame,
  ApiLinescore,
  ApiScoreUpdateChanges,
  ApiScoreUpdateLinescoreChanges,
} from '@/types/api';

function applyLinescoreChanges(
  oldLs: ApiLinescore | null | undefined,
  changes: ApiScoreUpdateLinescoreChanges,
): ApiLinescore {
  // Spread the existing linescore (or empty object if absent) and overlay each changed field.
  const next: ApiLinescore = { ...(oldLs ?? {}) };
  if (changes.inning !== undefined) next.inning = changes.inning.new ?? null;
  if (changes.inning_half !== undefined) {
    const half = changes.inning_half.new;
    next.inning_half = half === 'Top' || half === 'Bottom' ? half : null;
  }
  if (changes.balls !== undefined) next.balls = changes.balls.new ?? null;
  if (changes.strikes !== undefined) next.strikes = changes.strikes.new ?? null;
  if (changes.outs !== undefined) next.outs = changes.outs.new ?? null;
  // inning_state and bases aren't on the AppLinescore type — they fall through
  // to the cache as extra wire fields and don't render until the AppLinescore
  // type and adapter are updated to surface them.
  return next;
}

export function applyDiff(game: ApiGame, changes: ApiScoreUpdateChanges): ApiGame {
  const next: ApiGame = { ...game };

  if (changes.away_score !== undefined) {
    next.away_score = changes.away_score.new ?? next.away_score;
  }
  if (changes.home_score !== undefined) {
    next.home_score = changes.home_score.new ?? next.home_score;
  }
  if (changes.status !== undefined && changes.status.new !== null && changes.status.new !== undefined) {
    next.status = changes.status.new;
  }
  if (changes.detailed_state !== undefined && changes.detailed_state.new != null) {
    next.detailed_state = changes.detailed_state.new;
  }
  if (changes.linescore !== undefined) {
    next.linescore = applyLinescoreChanges(game.linescore, changes.linescore);
  }
  // Note: ApiGame doesn't currently include winProbability — that's an AppGame
  // concept the backend hasn't shipped yet. When it does, this is the place
  // to wire it through.
  return next;
}
