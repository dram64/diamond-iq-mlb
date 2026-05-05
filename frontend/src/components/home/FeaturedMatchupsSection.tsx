import { AiBadge } from '@/components/primitives/AiBadge';
import { SectionBar } from '@/components/primitives/SectionBar';
import { Skeleton } from '@/components/primitives/Skeleton';
import { TeamChip } from '@/components/primitives/TeamChip';
import type { AppFeaturedItem, AppGame, AppTeam } from '@/types/app';

/**
 * Today's Featured Matchups — two cards, AI editorial analysis paired
 * with the matchup headline (logos + team names) and a "View game" link.
 *
 * State machine:
 *   isLoading              → 2 skeleton cards
 *   isError                → 2 placeholder cards with API-unavailable footer
 *   featured.length === 0  → 2 placeholder cards with "Sample" footer
 *   has data               → render up to 2 real cards from `featured`
 */

interface FeaturedMatchupsSectionProps {
  featured: readonly AppFeaturedItem[];
  /** Resolves an AI item's gamePk to the matching scoreboard game. */
  gamesByPk: ReadonlyMap<number, AppGame>;
  isLoading: boolean;
  isError: boolean;
  isEmpty: boolean;
}

const PLACEHOLDER_BODIES: readonly (readonly string[])[] = [
  [
    "Two clubs in the same division enter tonight separated by under two games. Both have won three of their last five and feature top-third pitching staffs by ERA.",
    "Tonight's starters bring contrasting profiles — one a strikeout-first righty, the other a contact-suppressing soft-tosser whose ground-ball rate has climbed in his last three starts.",
    "The series turns on the bullpen. The visiting club has thrown 19 high-leverage innings in the last 10 days and may be a man short tonight if extras come into play.",
  ],
  [
    "A rematch of last year's wild-card series, with both clubs healthier than they were in October. The visitor is leading the league in barrel rate against fastballs since mid-April.",
    "The home club's ace is making his sixth start of the season; he's been velocity-stable through the first five and has not allowed more than two runs in any outing.",
    "Look for the pull-side defensive shifts — the visiting lineup has six left-handed bats with above-average pull rates, and the home club's infield positioning has been aggressive this year.",
  ],
];

const KICKERS = ['Featured matchup #1', 'Featured matchup #2'] as const;

export function FeaturedMatchupsSection({
  featured,
  gamesByPk,
  isLoading,
  isError,
  isEmpty,
}: FeaturedMatchupsSectionProps) {
  if (isLoading) {
    return <FeaturedSkeleton />;
  }

  const showPlaceholders = isError || isEmpty || featured.length === 0;
  const footer = isError
    ? 'API unavailable — showing sample copy.'
    : "Sample preview — featured matchup analyses will be generated daily by Claude Sonnet 4.6 from each day's slate.";

  return (
    <section>
      <SectionBar
        title="Today's Featured Matchups"
        subtitle="Deeper analysis on the day's most consequential games"
        badge={<AiBadge />}
      />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {showPlaceholders ? (
          [0, 1].map((i) => (
            <PlaceholderCard
              key={i}
              kicker={KICKERS[i] ?? 'Featured matchup'}
              body={PLACEHOLDER_BODIES[i] ?? PLACEHOLDER_BODIES[0]!}
              footer={footer}
            />
          ))
        ) : (
          featured.slice(0, 2).map((item) => (
            <FeaturedCard
              key={item.rank}
              item={item}
              game={gamesByPk.get(item.gamePk)}
            />
          ))
        )}
      </div>
    </section>
  );
}

interface FeaturedCardProps {
  item: AppFeaturedItem;
  game: AppGame | undefined;
}

function FeaturedCard({ item, game }: FeaturedCardProps) {
  if (!game && typeof console !== 'undefined') {
    console.warn(
      `Featured rank ${item.rank}: gamePk ${item.gamePk} not in scoreboard; rendering with placeholder headline`,
    );
  }
  const paragraphs = item.text.split(/\n\s*\n/).filter((p) => p.trim().length > 0);
  const kicker = `Featured matchup #${item.rank}`;

  return (
    <article className="flex flex-col gap-4 rounded-l border border-hairline-strong bg-white p-6 shadow-md">
      <div className="flex items-start justify-between gap-3">
        <span className="kicker">{kicker}</span>
        <AiBadge />
      </div>

      <MatchupHeadline game={game} />

      <div className="flex flex-col gap-3 text-[14px] leading-relaxed text-paper-3">
        {paragraphs.map((p, i) => (
          <p key={i} className="m-0">
            {p}
          </p>
        ))}
      </div>

      {/* dedicated /live/:gameId page removed; the card is the
          full surface for these matchups now. */}
    </article>
  );
}

function PlaceholderCard({
  kicker,
  body,
  footer,
}: {
  kicker: string;
  body: readonly string[];
  footer: string;
}) {
  return (
    <article className="flex flex-col gap-4 rounded-l border border-hairline-strong bg-white p-6 shadow-md">
      <div className="flex items-start justify-between gap-3">
        <span className="kicker">{kicker}</span>
        <AiBadge />
      </div>

      <MatchupHeadline game={undefined} />

      <div className="flex flex-col gap-3 text-[14px] leading-relaxed text-paper-3">
        {body.map((p, i) => (
          <p key={i} className="m-0 italic">
            {p}
          </p>
        ))}
      </div>

      <div className="border-t border-hairline pt-3 text-[11px] italic text-paper-4">
        {footer}
      </div>
    </article>
  );
}

function MatchupHeadline({ game }: { game: AppGame | undefined }) {
  if (!game) {
    return (
      <div className="flex items-center justify-center gap-3 rounded-m bg-surface-2 px-4 py-3 text-paper-4">
        <PlaceholderTeam label="Two" />
        <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-paper-5">
          vs
        </span>
        <PlaceholderTeam label="Clubs" />
      </div>
    );
  }
  return (
    <div className="flex items-center justify-center gap-4 rounded-m bg-surface-2 px-4 py-3">
      <SideTeam team={game.away} />
      <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-paper-5">
        vs
      </span>
      <SideTeam team={game.home} />
    </div>
  );
}

function SideTeam({ team }: { team: AppTeam }) {
  return (
    <div className="flex items-center gap-2.5">
      <TeamChip
        abbr={team.abbreviation}
        color={team.primaryColor}
        logoPath={team.logoPath}
        size={36}
      />
      <div className="flex flex-col leading-tight">
        <span className="text-[14px] font-bold -tracking-[0.01em] text-paper">
          {team.abbreviation}
        </span>
        <span className="text-[10.5px] text-paper-4">{team.teamName}</span>
      </div>
    </div>
  );
}

function PlaceholderTeam({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2.5">
      <span
        className="inline-flex h-9 w-9 items-center justify-center rounded-s bg-surface-3 text-[10px] font-semibold uppercase text-paper-5"
        aria-hidden="true"
      >
        —
      </span>
      <span className="text-[14px] font-semibold text-paper-4">{label}</span>
    </div>
  );
}

function FeaturedSkeleton() {
  return (
    <section data-testid="featured-skeleton">
      <SectionBar
        title="Today's Featured Matchups"
        subtitle="Deeper analysis on the day's most consequential games"
        badge={<AiBadge />}
      />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {[0, 1].map((i) => (
          <div
            key={i}
            className="flex flex-col gap-4 rounded-l border border-hairline-strong bg-white p-6 shadow-md"
          >
            <Skeleton className="h-3 w-1/3" />
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-11/12" />
            <Skeleton className="h-4 w-9/12" />
          </div>
        ))}
      </div>
    </section>
  );
}
