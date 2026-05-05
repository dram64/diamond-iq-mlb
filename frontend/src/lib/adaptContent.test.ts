import { describe, expect, it } from 'vitest';

import { adaptContent, adaptContentItem, adaptFeaturedItem } from './adapters';
import type { ApiContentResponse, ApiFeaturedItem } from '@/types/api';

describe('adaptContentItem', () => {
  it('coerces snake_case to camelCase and parses generated_at_utc', () => {
    const result = adaptContentItem({
      text: 'Body.',
      content_type: 'RECAP',
      model_id: 'us.anthropic.claude-sonnet-4-6',
      generated_at_utc: '2026-04-26T15:00:00+00:00',
      game_pk: 1001,
    });
    expect(result.text).toBe('Body.');
    expect(result.contentType).toBe('RECAP');
    expect(result.modelId).toBe('us.anthropic.claude-sonnet-4-6');
    expect(result.gamePk).toBe(1001);
    expect(result.generatedAt).toBeInstanceOf(Date);
    expect(result.generatedAt.toISOString()).toBe('2026-04-26T15:00:00.000Z');
  });

  it('falls back to epoch when generated_at_utc is missing/invalid', () => {
    const item = adaptContentItem({
      text: 't',
      content_type: 'PREVIEW',
      model_id: 'm',
      generated_at_utc: 'not-a-date',
      game_pk: 1,
    });
    expect(item.generatedAt.getTime()).toBe(0);
  });
});

describe('adaptFeaturedItem', () => {
  it('preserves rank alongside the base content fields', () => {
    const wire: ApiFeaturedItem = {
      text: 'F.',
      content_type: 'FEATURED',
      model_id: 'm',
      generated_at_utc: '2026-04-26T15:00:00+00:00',
      game_pk: 3001,
      rank: 2,
    };
    const out = adaptFeaturedItem(wire);
    expect(out.rank).toBe(2);
    expect(out.contentType).toBe('FEATURED');
    expect(out.gamePk).toBe(3001);
  });
});

describe('adaptContent', () => {
  it('returns three empty lists when the response is empty', () => {
    const wire: ApiContentResponse = {
      date: '2026-04-26',
      recap: [],
      previews: [],
      featured: [],
    };
    const out = adaptContent(wire);
    expect(out).toEqual({
      date: '2026-04-26',
      recap: [],
      previews: [],
      featured: [],
    });
  });

  it('maps every category through its adapter', () => {
    const wire: ApiContentResponse = {
      date: '2026-04-26',
      recap: [
        {
          text: 'r',
          content_type: 'RECAP',
          model_id: 'm',
          generated_at_utc: '2026-04-26T15:00:00+00:00',
          game_pk: 1,
        },
      ],
      previews: [
        {
          text: 'p',
          content_type: 'PREVIEW',
          model_id: 'm',
          generated_at_utc: '2026-04-26T15:00:00+00:00',
          game_pk: 2,
        },
      ],
      featured: [
        {
          text: 'f',
          content_type: 'FEATURED',
          model_id: 'm',
          generated_at_utc: '2026-04-26T15:00:00+00:00',
          game_pk: 3,
          rank: 1,
        },
      ],
    };
    const out = adaptContent(wire);
    expect(out.recap[0]?.gamePk).toBe(1);
    expect(out.previews[0]?.gamePk).toBe(2);
    expect(out.featured[0]?.rank).toBe(1);
  });
});
