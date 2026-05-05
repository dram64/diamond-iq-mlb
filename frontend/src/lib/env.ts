/**
 * Typed access to the frontend's compile-time environment.
 *
 * Vite injects values from `.env*` files into `import.meta.env` at build time.
 * We re-export them through this module so consumers don't sprinkle
 * `import.meta.env.VITE_*` reads across the codebase, and so the runtime
 * fails loudly at boot if a required variable is missing rather than at the
 * unlucky line where the value is first dereferenced.
 */

function required(name: string, raw: string | undefined): string {
  if (typeof raw !== 'string' || raw.length === 0) {
    throw new Error(
      `Missing required environment variable ${name}. ` +
        `Set it in .env.development, .env.local, or your hosting provider.`,
    );
  }
  return raw;
}

function flag(raw: string | undefined): boolean {
  return raw === 'true' || raw === '1';
}

/** Trim a trailing slash so callers can always concatenate `${API_URL}/path`. */
function stripTrailingSlash(url: string): string {
  return url.replace(/\/+$/, '');
}

export const API_URL: string = stripTrailingSlash(
  required('VITE_API_URL', import.meta.env.VITE_API_URL),
);

/** WebSocket endpoint for the real-time score-update pipeline. wss:// scheme. */
export const WS_URL: string = stripTrailingSlash(
  required('VITE_WS_URL', import.meta.env.VITE_WS_URL),
);

export const HIDE_DEMO_BADGES: boolean = flag(import.meta.env.VITE_HIDE_DEMO_BADGES);
