import { FeaturedMatchupHero } from '@/components/home/FeaturedMatchupHero';
import { LiveGamesStrip } from '@/components/home/LiveGamesStrip';
import { MiniStandingsTile } from '@/components/home/MiniStandingsTile';
import { NavCard } from '@/components/home/NavCard';
import { RecentFinalsTile } from '@/components/home/RecentFinalsTile';
import { StandoutPerformancesPanel } from '@/components/home/StandoutPerformancesPanel';
import { StatcastLeaderOfWeekTile } from '@/components/home/StatcastLeaderOfWeekTile';
import { TeamSpotlightTile } from '@/components/home/TeamSpotlightTile';
import { TopBatSpeedTile } from '@/components/home/TopBatSpeedTile';
import { ErrorBanner } from '@/components/primitives/ErrorBanner';
import { useScoreboard } from '@/hooks/useScoreboard';

export function HomePage() {
  const { liveGames, isError, error, isFetching, refetch, lastUpdatedAt } = useScoreboard();

  return (
    <div className="page-editorial flex flex-col gap-10">
      <FeaturedMatchupHero />

      {isError && (
        <ErrorBanner
          title="Couldn't load today's games"
          message={error?.message ?? 'Please try again in a moment.'}
          onRetry={refetch}
        />
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1.55fr_1fr]">
        <div className="flex flex-col gap-6">
          <StandoutPerformancesPanel />
          <RecentFinalsTile />
          <TeamSpotlightTile />
        </div>
        <div className="flex flex-col gap-3">
          <MiniStandingsTile />
          <TopBatSpeedTile />
          <StatcastLeaderOfWeekTile />
          <div className="grid grid-cols-1 gap-3 pt-1">
            <NavCard
              to="/compare-players"
              kicker="Compare"
              title="Compare players"
              description="Hexagonal radar over six hero stats. Up to four players at once."
            />
            <NavCard
              to="/compare-teams"
              kicker="Compare"
              title="Compare teams"
              description="Two clubs, six aggregate axes, full numerical detail."
            />
            <NavCard
              to="/stats"
              kicker="Stats"
              title="Stat explorer"
              description="Season leaderboards across hitting and pitching."
            />
            <NavCard
              to="/teams"
              kicker="Teams"
              title="All 30 clubs"
              description="Browse by division. Logos, records, deep team pages."
            />
          </div>
        </div>
      </div>

      <LiveGamesStrip
        liveGames={liveGames}
        isFetching={isFetching}
        lastUpdatedAt={lastUpdatedAt}
      />
    </div>
  );
}
