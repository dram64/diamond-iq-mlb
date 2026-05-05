export interface RecapTopPerformer {
  name: string;
  team: string;
  line: string;
  context?: string | null;
}

export interface RecapHeadToHeadSide {
  name: string;
  line: string;
}

export interface RecapHeadToHead {
  player_a: RecapHeadToHeadSide;
  player_b: RecapHeadToHeadSide;
  takeaway: string;
}

export interface AnalyticalRecap {
  headline: string;
  score_summary: string;
  top_performers: RecapTopPerformer[];
  head_to_head: RecapHeadToHead[];
  tidbits: string[];
}

/** Try to extract <json>{...}</json> from a Bedrock text payload. */
export function parseAnalyticalRecap(text: string | null | undefined): AnalyticalRecap | null {
  if (!text) return null;
  const match = text.match(/<json>([\s\S]*?)<\/json>/i);
  const body = match ? match[1].trim() : text.trim();
  try {
    const parsed = JSON.parse(body) as Partial<AnalyticalRecap>;
    if (typeof parsed.headline !== 'string') return null;
    return {
      headline: parsed.headline,
      score_summary: parsed.score_summary ?? '',
      top_performers: Array.isArray(parsed.top_performers) ? parsed.top_performers : [],
      head_to_head: Array.isArray(parsed.head_to_head) ? parsed.head_to_head : [],
      tidbits: Array.isArray(parsed.tidbits) ? parsed.tidbits : [],
    };
  } catch {
    return null;
  }
}
