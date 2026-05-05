import { Link, useRouteError } from 'react-router-dom';

export function NotFoundPage() {
  const err = useRouteError();
  return (
    <section>
      <div className="kicker mb-2">404</div>
      <h1>Not found</h1>
      <p className="mt-2 text-paper-3">
        {err instanceof Error ? err.message : 'That route does not exist.'}
      </p>
      <Link to="/" className="mt-4 inline-block text-accent hover:text-accent-glow">
        ← Back to Today
      </Link>
    </section>
  );
}
