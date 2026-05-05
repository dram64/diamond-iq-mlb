import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

interface LinkButtonProps {
  to: string;
  children: ReactNode;
}

/** Tiny accent-colored "Open X →" affordance used in section headers. */
export function LinkButton({ to, children }: LinkButtonProps) {
  return (
    <Link
      to={to}
      className="text-xs font-semibold text-accent hover:text-accent-glow"
    >
      {children}
    </Link>
  );
}
