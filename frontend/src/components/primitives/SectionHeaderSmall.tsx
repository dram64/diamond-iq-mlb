interface SectionHeaderSmallProps {
  kicker: string;
  title: string;
}

/** Kicker + h3 pair used above in-card sections. */
export function SectionHeaderSmall({ kicker, title }: SectionHeaderSmallProps) {
  return (
    <div className="mb-2 flex flex-col gap-1">
      <span className="kicker">{kicker}</span>
      <h3 className="text-xl">{title}</h3>
    </div>
  );
}
