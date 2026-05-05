/** Format a batting-style decimal (0.326 → ".326"). */
export function formatBA(value: number): string {
  if (!Number.isFinite(value)) return '.000';
  const clamped = Math.max(0, Math.min(1, value));
  return clamped.toFixed(3).replace(/^0/, '');
}

/** Format a run differential with explicit sign ("+112" / "-14"). */
export function formatRunDiff(value: number): string {
  if (value > 0) return `+${value}`;
  return `${value}`;
}

/** "top" | "bot" → "▲" / "▼" arrow for an inning indicator. */
export function inningArrow(half: 'top' | 'bot'): '▲' | '▼' {
  return half === 'top' ? '▲' : '▼';
}
