import { BaseDiamond } from '@/components/primitives/BaseDiamond';
import { TeamChip } from '@/components/primitives/TeamChip';
import type { AppGame, AppInningHalf, AppTeam } from '@/types/app';

interface LiveGameCardProps {
  game: AppGame;
}

const EMDASH = '—';

export function LiveGameCard({ game }: LiveGameCardProps) {
  const inning = game.linescore?.inning;
  const half = game.linescore?.inningHalf;
  const balls = game.linescore?.balls ?? 0;
  const strikes = game.linescore?.strikes ?? 0;
  const outs = game.linescore?.outs ?? 0;
  const showMatchupRow = game.batter !== undefined || game.pitcher !== undefined;
  const showWinProbability = game.winProbability !== undefined;

  // as an at-a-glance scoreboard tile (no click-through) since the live
  // scoreboard remains a meaningful surface on the home page.
  return (
    <div className="group flex flex-col gap-2 rounded-l border border-hairline-strong bg-white p-3 shadow-sm">

      <div className="flex items-center justify-between">
        <span className="inline-flex items-center gap-1.5 text-[10.5px] font-bold uppercase tracking-[0.08em] text-live">
          <span className="live-dot" /> Live
        </span>
        <span className="flex items-center gap-1 text-[11px] text-paper-3">
          {half && <InningArrow half={half} />}
          <span className="mono font-semibold">
            {half === 'top' ? 'Top' : half === 'bot' ? 'Bot' : ''}
            {inning != null ? ` ${inning}` : ''}
            {inning == null && !half && EMDASH}
          </span>
        </span>
      </div>

      {/* teams + scores */}
      <div className="flex flex-col gap-2">
        <GameTeamLine
          t={game.away}
          score={game.awayScore}
          leading={game.awayScore > game.homeScore}
        />
        <GameTeamLine
          t={game.home}
          score={game.homeScore}
          leading={game.homeScore > game.awayScore}
        />
      </div>

      {/* diamond + count + matchup */}
      <div className="flex items-center gap-3.5 border-y border-hairline py-2.5">
        <BaseDiamond bases={game.bases} size={36} />
        <div className="flex flex-1 flex-col gap-1.5">
          <div className="flex items-center gap-3">
            <CountMini label="B" value={balls} max={3} />
            <CountMini label="S" value={strikes} max={2} />
            <CountMini label="O" value={outs} max={2} red />
          </div>
          {showMatchupRow ? (
            <div className="text-[11px] leading-snug text-paper-4">
              <span className="font-semibold text-paper-2">{game.batter ?? EMDASH}</span>
              {' vs '}
              <span className="font-semibold text-paper-2">{game.pitcher ?? EMDASH}</span>
            </div>
          ) : (
            <div className="text-[11px] leading-snug text-paper-4">
              {game.detailedState}
            </div>
          )}
        </div>
      </div>

      {showWinProbability && (
        <WinProbabilityRow
          away={game.away}
          home={game.home}
          homeWinProbability={game.winProbability ?? 50}
        />
      )}
    </div>
  );
}

function InningArrow({ half }: { half: AppInningHalf }) {
  return (
    <svg width="8" height="10" viewBox="0 0 8 10" className="block" aria-hidden="true">
      {half === 'top' ? (
        <path d="M4 1 L7 6 L1 6 Z" fill="#4b5563" />
      ) : (
        <path d="M4 9 L7 4 L1 4 Z" fill="#4b5563" />
      )}
    </svg>
  );
}

function GameTeamLine({
  t,
  score,
  leading,
}: {
  t: AppTeam;
  score: number;
  leading: boolean;
}) {
  return (
    <div className="flex items-center gap-2.5">
      <TeamChip abbr={t.abbreviation} color={t.primaryColor} logoPath={t.logoPath} size={26} />
      <div className="min-w-0 flex-1">
        <div className="text-sm font-bold -tracking-[0.01em] text-paper">
          {t.locationName || t.fullName}
        </div>
        <div className="mono text-[10.5px] text-paper-4">{t.teamName}</div>
      </div>
      <div
        className={[
          'mono text-[26px] font-bold leading-none',
          leading ? 'text-paper' : 'text-paper-3',
        ].join(' ')}
      >
        {score}
      </div>
    </div>
  );
}

function CountMini({
  label,
  value,
  max,
  red,
}: {
  label: string;
  value: number;
  max: number;
  red?: boolean;
}) {
  const onClass = red ? 'bg-live' : 'bg-accent';
  return (
    <div className="flex items-center gap-1">
      <span className="text-[9px] font-bold tracking-[0.04em] text-paper-4">{label}</span>
      <div className="flex gap-[3px]">
        {Array.from({ length: max }).map((_, i) => (
          <span
            key={i}
            className={[
              'h-1.5 w-1.5 rounded-full',
              i < value ? onClass : 'bg-[#e5e7eb]',
            ].join(' ')}
          />
        ))}
      </div>
    </div>
  );
}

function WinProbabilityRow({
  away,
  home,
  homeWinProbability,
}: {
  away: AppTeam;
  home: AppTeam;
  homeWinProbability: number;
}) {
  const wpAway = 100 - homeWinProbability;
  const wpHome = homeWinProbability;
  return (
    <div>
      <div className="mb-1.5 flex items-center gap-2">
        <span className="whitespace-nowrap text-[10px] font-semibold uppercase tracking-[0.06em] text-paper-4">
          Win Prob
        </span>
      </div>
      <div className="flex items-center gap-1.5">
        <span
          className={[
            'mono w-8 text-[11px]',
            wpAway > wpHome ? 'font-bold text-paper' : 'text-paper-4',
          ].join(' ')}
        >
          {wpAway}%
        </span>
        <div className="flex h-1.5 flex-1 overflow-hidden rounded-s bg-surface-3">
          <div style={{ width: `${wpAway}%`, background: away.primaryColor || '#27272a', opacity: 0.9 }} />
          <div style={{ width: `${wpHome}%`, background: home.primaryColor || '#27272a', opacity: 0.9 }} />
        </div>
        <span
          className={[
            'mono w-8 text-right text-[11px]',
            wpHome > wpAway ? 'font-bold text-paper' : 'text-paper-4',
          ].join(' ')}
        >
          {wpHome}%
        </span>
      </div>
    </div>
  );
}
