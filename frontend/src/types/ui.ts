/** AI-generated insight card shown on the home page. */
export interface AIInsight {
  topic: string;
  blurb: string;
  /** Freeform tag, e.g. "STR · KNG" or "Trend". */
  tag: string;
}

/** Key-value tile shown under the featured-game hero. */
export interface FeaturedStat {
  label: string;
  value: string;
  sub: string;
  accent?: boolean;
}
