import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { RouterProvider } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { router } from './router';

// instead of loaded from fonts.googleapis.com so the critical render path
// no longer depends on a third-party CDN. Latin-only variants prune the
// cyrillic / latin-ext / vietnamese / greek subsets from the CSS bundle —
// dropped CSS from ~69 KB to ~25 KB and eliminated ~30 unused font files
// from the build.
import '@fontsource/inter/latin-400.css';
import '@fontsource/inter/latin-500.css';
import '@fontsource/inter/latin-600.css';
import '@fontsource/inter/latin-700.css';
import '@fontsource/inter/latin-800.css';
import '@fontsource/jetbrains-mono/latin-400.css';
import '@fontsource/jetbrains-mono/latin-500.css';
import '@fontsource/jetbrains-mono/latin-600.css';

import './index.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      // Hooks opt in to refetchOnWindowFocus per-query.
      refetchOnWindowFocus: false,
      // Retry transient failures twice with TanStack's default exponential
      // backoff. Tests override via QueryClient defaults in their wrapper.
      retry: 2,
    },
  },
});

const rootEl = document.getElementById('root');
if (!rootEl) throw new Error('Root element #root not found');

createRoot(rootEl).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
);
