/**
 * Tests for useGameSubscription.
 *
 * We don't try to drive the real WebSocket manager end-to-end here (that's
 * covered by websocket.test.ts). Instead we mock the manager module so the
 * hook's React-level behavior — subscribe-on-mount, unsubscribe-on-unmount,
 * cache-update-on-message — is testable in isolation.
 */

import { renderHook, act } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

import type { GameDetailResponse } from '@/types/api';

// vi.mock is hoisted to the top of the file; vi.hoisted lifts our shared
// mock object alongside it so the factory can refer to it without a TDZ error.
type MockState = 'CLOSED' | 'CONNECTING' | 'OPEN' | 'CLOSING';
const { mockManager } = vi.hoisted(() => {
  type AnyMsg = { type: string; game_pk: number; timestamp: string; changes: unknown };
  const manager = {
    state: 'CLOSED' as MockState,
    messageListeners: new Set<(msg: AnyMsg) => void>(),
    stateListeners: new Set<(s: MockState) => void>(),
    subscribed: new Set<number>(),
    connect: vi.fn(),
    disconnect: vi.fn(),
    subscribe: vi.fn((pk: number) => {
      manager.subscribed.add(pk);
    }),
    unsubscribe: vi.fn((pk: number) => {
      manager.subscribed.delete(pk);
    }),
    onMessage: vi.fn((cb: (msg: AnyMsg) => void) => {
      manager.messageListeners.add(cb);
      return () => manager.messageListeners.delete(cb);
    }),
    onStateChange: vi.fn((cb: (s: MockState) => void) => {
      cb(manager.state);
      manager.stateListeners.add(cb);
      return () => manager.stateListeners.delete(cb);
    }),
    getState: vi.fn(() => manager.state),
    pushMessage(msg: AnyMsg) {
      for (const l of manager.messageListeners) l(msg);
    },
  };
  return { mockManager: manager };
});

vi.mock('@/lib/websocket', () => ({
  websocketManager: mockManager,
}));

// Now import the hook (after the vi.mock wires the alias).
import { useGameSubscription } from './useGameSubscription';

const SAMPLE_RESPONSE: GameDetailResponse = {
  game: {
    game_pk: 822909,
    date: '2026-04-27',
    status: 'live',
    detailed_state: 'In Progress',
    away: { id: 1, name: 'Away', abbreviation: 'A' },
    home: { id: 2, name: 'Home', abbreviation: 'H' },
    away_score: 3,
    home_score: 0,
    start_time_utc: '2026-04-27T00:05:00Z',
    linescore: { inning: 5, inning_half: 'Top', outs: 1 },
  },
};

function makeWrapper() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0, staleTime: 0 },
    },
  });
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  }
  return { client, Wrapper };
}

beforeEach(() => {
  mockManager.state = 'CLOSED';
  mockManager.messageListeners.clear();
  mockManager.stateListeners.clear();
  mockManager.subscribed.clear();
  vi.clearAllMocks();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('useGameSubscription', () => {
  it('connects and subscribes on mount when given a numeric gamePk', () => {
    const { Wrapper } = makeWrapper();
    renderHook(() => useGameSubscription(822909), { wrapper: Wrapper });
    expect(mockManager.connect).toHaveBeenCalled();
    expect(mockManager.subscribe).toHaveBeenCalledWith(822909);
  });

  it('does not subscribe when gamePk is undefined', () => {
    const { Wrapper } = makeWrapper();
    renderHook(() => useGameSubscription(undefined), { wrapper: Wrapper });
    expect(mockManager.subscribe).not.toHaveBeenCalled();
  });

  it('unsubscribes on unmount', () => {
    const { Wrapper } = makeWrapper();
    const { unmount } = renderHook(() => useGameSubscription(123), { wrapper: Wrapper });
    expect(mockManager.subscribe).toHaveBeenCalledWith(123);
    unmount();
    expect(mockManager.unsubscribe).toHaveBeenCalledWith(123);
  });

  it('reconciles incoming score_update messages into the matching cache entry', () => {
    const { client, Wrapper } = makeWrapper();
    client.setQueryData(['game', 822909, '2026-04-27'], SAMPLE_RESPONSE);

    renderHook(() => useGameSubscription(822909), { wrapper: Wrapper });

    act(() => {
      mockManager.pushMessage({
        type: 'score_update',
        game_pk: 822909,
        timestamp: '2026-04-27T01:23:45Z',
        changes: {
          away_score: { old: 3, new: 4 },
          linescore: { outs: { old: 1, new: 0 } },
        },
      });
    });

    const cached = client.getQueryData<GameDetailResponse>([
      'game',
      822909,
      '2026-04-27',
    ]);
    expect(cached?.game.away_score).toBe(4);
    expect(cached?.game.linescore?.outs).toBe(0);
    // Untouched fields preserved.
    expect(cached?.game.home_score).toBe(0);
    expect(cached?.game.linescore?.inning).toBe(5);
  });

  it('ignores messages for a different gamePk', () => {
    const { client, Wrapper } = makeWrapper();
    client.setQueryData(['game', 822909, '2026-04-27'], SAMPLE_RESPONSE);

    renderHook(() => useGameSubscription(822909), { wrapper: Wrapper });

    act(() => {
      mockManager.pushMessage({
        type: 'score_update',
        game_pk: 999999,
        timestamp: '2026-04-27T01:23:45Z',
        changes: { away_score: { old: 3, new: 99 } },
      });
    });

    const cached = client.getQueryData<GameDetailResponse>([
      'game',
      822909,
      '2026-04-27',
    ]);
    expect(cached?.game.away_score).toBe(3); // unchanged
  });

  it('exposes the connection state from the manager', () => {
    mockManager.state = 'OPEN';
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useGameSubscription(1), { wrapper: Wrapper });
    expect(result.current.connectionState).toBe('OPEN');
  });
});
