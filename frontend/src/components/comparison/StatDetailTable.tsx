import type { ComparePlayer } from '@/types/compare';
import { PLAYER_DETAIL_GROUPS, pickWinner, type StatRef } from './stat-extract';

interface StatDetailTableProps {
  players: readonly ComparePlayer[];
}

export function StatDetailTable({ players }: StatDetailTableProps) {
  if (players.length < 2) return null;

  // Drop groups where every row is null for every player — keeps the
  // table tidy when comparing two hitters (the pitcher-arsenal group
  // has no data) or two pitchers.
  const visibleGroups = PLAYER_DETAIL_GROUPS.filter((group) =>
    group.rows.some((row) => players.some((p) => row.pick(p) !== null)),
  );

  return (
    <div className="rounded-l border border-hairline-strong bg-surface-elevated p-5 shadow-sm">
      <div className="kicker mb-3 text-accent-leather">Numerical detail</div>
      <div className="flex flex-col gap-5">
        {visibleGroups.map((group) => (
          <Group key={group.title} title={group.title} rows={group.rows} players={players} />
        ))}
      </div>
    </div>
  );
}

function Group({
  title,
  rows,
  players,
}: {
  title: string;
  rows: StatRef[];
  players: readonly ComparePlayer[];
}) {
  return (
    <div>
      <div className="kicker mb-2 text-paper-ink-soft">{title}</div>
      <div
        className="grid items-baseline gap-x-3 gap-y-1.5"
        style={{
          gridTemplateColumns: `120px repeat(${players.length}, minmax(0, 1fr))`,
        }}
      >
        {/* Header row: player names */}
        <div />
        {players.map((p) => (
          <div
            key={p.person_id}
            className="truncate text-right text-[11px] font-semibold text-paper-ink-muted"
          >
            {p.metadata.full_name}
          </div>
        ))}

        {/* Body */}
        {rows.map((row) => (
          <Row key={row.token} row={row} players={players} />
        ))}
      </div>
    </div>
  );
}

function Row({
  row,
  players,
}: {
  row: StatRef;
  players: readonly ComparePlayer[];
}) {
  const values = players.map((p) => row.pick(p));

  // Pick the winner across the row.
  let winnerIdx: number | null = null;
  for (let i = 0; i < values.length; i++) {
    if (values[i] == null) continue;
    if (winnerIdx === null) {
      winnerIdx = i;
      continue;
    }
    const cmp = pickWinner(values[i], values[winnerIdx], row.ascending);
    if (cmp === 'a') winnerIdx = i;
  }

  return (
    <>
      <span className="text-[12.5px] text-paper-ink">{row.label}</span>
      {values.map((v, i) => {
        const isWinner = winnerIdx === i;
        return (
          <span
            key={i}
            className={[
              'mono text-right text-[13px]',
              isWinner ? 'font-bold text-accent-leather' : 'text-paper-ink-muted',
            ].join(' ')}
          >
            {row.format(v)}
          </span>
        );
      })}
    </>
  );
}
