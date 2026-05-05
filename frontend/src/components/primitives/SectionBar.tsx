import type { ReactNode } from 'react';

interface SectionBarProps {
  title: string;
  subtitle?: string;
  badge?: ReactNode;
  right?: ReactNode;
  /** Smaller type for secondary sections. */
  small?: boolean;
}

/** Title row above each home-page section — title + optional subtitle/badge on the left, action on the right. */
export function SectionBar({ title, subtitle, badge, right, small }: SectionBarProps) {
  return (
    <div className="mb-3.5 flex items-baseline justify-between border-b border-hairline-strong pb-3">
      <div className="flex items-center gap-3">
        <h2 className={small ? 'text-base font-bold' : 'text-xl font-bold'}>{title}</h2>
        {subtitle && <span className="text-[13px] text-paper-4">{subtitle}</span>}
        {badge}
      </div>
      {right}
    </div>
  );
}
