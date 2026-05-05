import { Link } from 'react-router-dom';

interface NavCardProps {
  to: string;
  kicker: string;
  title: string;
  description: string;
}

export function NavCard({ to, kicker, title, description }: NavCardProps) {
  return (
    <Link
      to={to}
      className="group flex items-center justify-between gap-4 rounded-l border border-hairline-strong bg-surface-elevated px-5 py-4 shadow-sm transition-all duration-200 ease-out hover:border-accent-leather/50 hover:shadow-md"
    >
      <div className="min-w-0 flex-1">
        <div className="kicker mb-1 text-accent-leather">{kicker}</div>
        <div className="text-[15px] font-bold leading-tight -tracking-[0.005em] text-paper-ink">
          {title}
        </div>
        <div className="mt-0.5 text-[12px] leading-snug text-paper-ink-muted">
          {description}
        </div>
      </div>
      <span
        aria-hidden="true"
        className="text-[22px] leading-none text-accent-gold transition-transform duration-200 ease-out group-hover:translate-x-0.5"
      >
        →
      </span>
    </Link>
  );
}
