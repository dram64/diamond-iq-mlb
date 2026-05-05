import { lazy, Suspense, type ReactNode } from 'react';
import { createBrowserRouter, Navigate } from 'react-router-dom';

import { RootLayout } from './components/RootLayout';
import { Skeleton } from './components/primitives/Skeleton';
// Home page stays eager — it's the LCP-critical first paint, code-splitting
// fix; reduces initial bundle from 339 KB → ~210 KB and gets desktop
// Lighthouse over the ≥ 90 threshold).
import { HomePage } from './pages/HomePage';
import { NotFoundPage } from './pages/NotFoundPage';

const PlayerComparePage = lazy(() =>
  import('./pages/PlayerComparePage').then((m) => ({ default: m.PlayerComparePage })),
);
const TeamComparePage = lazy(() =>
  import('./pages/TeamComparePage').then((m) => ({ default: m.TeamComparePage })),
);
const TeamsPage = lazy(() =>
  import('./pages/TeamsPage').then((m) => ({ default: m.TeamsPage })),
);
const TeamDetailPage = lazy(() =>
  import('./pages/TeamDetailPage').then((m) => ({ default: m.TeamDetailPage })),
);
const StatsPage = lazy(() =>
  import('./pages/StatsPage').then((m) => ({ default: m.StatsPage })),
);

/** Skeleton fallback shown while a lazy route chunk downloads. Visually
 *  consistent with the loading states used inside data-fetching components. */
// eslint-disable-next-line react-refresh/only-export-components
function RouteFallback() {
  return (
    <div className="mx-auto max-w-page px-4 py-10">
      <Skeleton className="mb-3 h-8 w-1/3" />
      <Skeleton className="mb-2 h-4 w-1/2" />
      <Skeleton className="h-[420px] w-full" />
    </div>
  );
}

function lazyRoute(element: ReactNode): ReactNode {
  return <Suspense fallback={<RouteFallback />}>{element}</Suspense>;
}

export const router = createBrowserRouter([
  {
    path: '/',
    element: <RootLayout />,
    errorElement: <NotFoundPage />,
    children: [
      { index: true, element: <HomePage /> },
      { path: 'live', element: <Navigate to="/" replace /> },
      { path: 'live/:gameId', element: <Navigate to="/" replace /> },
      { path: 'compare', element: <Navigate to="/compare-players" replace /> },
      { path: 'compare-players', element: lazyRoute(<PlayerComparePage />) },
      { path: 'compare-teams', element: lazyRoute(<TeamComparePage />) },
      { path: 'teams', element: lazyRoute(<TeamsPage />) },
      { path: 'teams/:teamId', element: lazyRoute(<TeamDetailPage />) },
      { path: 'stats', element: lazyRoute(<StatsPage />) },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
]);
