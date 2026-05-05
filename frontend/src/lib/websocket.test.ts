/**
 * Tests for the singleton WebSocket manager.
 *
 * We stub the global `WebSocket` constructor with a controllable mock that
 * exposes hooks for triggering open/message/close. The manager singleton is
 * shared module-state, so we reset it between tests.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { websocketManager } from './websocket';
import type { ApiScoreUpdateMessage } from '@/types/api';

// ── Mock WebSocket ───────────────────────────────────────────────────

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  static OPEN = 1;
  url: string;
  onopen: (() => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  sent: string[] = [];
  closedManually = false;

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }
  send(data: string): void {
    this.sent.push(data);
  }
  close(): void {
    this.closedManually = true;
    setTimeout(() => this.onclose?.(), 0);
  }
  // Test helpers ────────────────────────────────────────────────────
  triggerOpen(): void {
    this.onopen?.();
  }
  triggerMessage(payload: unknown): void {
    this.onmessage?.({ data: JSON.stringify(payload) });
  }
  triggerClose(): void {
    this.onclose?.();
  }
}

const SCORE_UPDATE: ApiScoreUpdateMessage = {
  type: 'score_update',
  game_pk: 822909,
  timestamp: '2026-04-27T01:23:45Z',
  changes: { away_score: { old: 3, new: 4 } },
};

beforeEach(() => {
  MockWebSocket.instances = [];
  vi.useFakeTimers();
  vi.stubGlobal('WebSocket', MockWebSocket);
  // Reset the singleton state between tests by forcing a manual disconnect.
  websocketManager.disconnect();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

function currentSocket(): MockWebSocket {
  const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1];
  if (!ws) throw new Error('no WebSocket instance constructed yet');
  return ws;
}

describe('websocketManager', () => {
  it('opens the WebSocket on first subscribe and transitions to OPEN', () => {
    websocketManager.subscribe(1);
    expect(MockWebSocket.instances).toHaveLength(1);
    expect(websocketManager.getState()).toBe('CONNECTING');

    currentSocket().triggerOpen();
    expect(websocketManager.getState()).toBe('OPEN');
  });

  it('flushes queued subscribes after open and serializes them as JSON', () => {
    websocketManager.subscribe(101);
    websocketManager.subscribe(202);
    currentSocket().triggerOpen();

    const sent = currentSocket().sent.map((s) => JSON.parse(s));
    expect(sent).toEqual([
      { action: 'subscribe', game_pk: 101 },
      { action: 'subscribe', game_pk: 202 },
    ]);
  });

  it('re-subscribes to all tracked games after a reconnect', () => {
    websocketManager.subscribe(101);
    websocketManager.subscribe(202);
    const first = currentSocket();
    first.triggerOpen();
    first.sent.length = 0; // ignore initial flush

    // Simulate disconnect → reconnect cycle.
    first.triggerClose();
    expect(websocketManager.getState()).toBe('CLOSED');

    // Advance the 1s backoff timer.
    vi.advanceTimersByTime(1000);
    const second = currentSocket();
    expect(second).not.toBe(first);
    second.triggerOpen();

    const sent = second.sent.map((s) => JSON.parse(s));
    expect(sent).toEqual([
      { action: 'subscribe', game_pk: 101 },
      { action: 'subscribe', game_pk: 202 },
    ]);
  });

  it('dispatches incoming score_update messages to listeners', () => {
    const listener = vi.fn();
    const off = websocketManager.onMessage(listener);
    websocketManager.subscribe(822909);
    currentSocket().triggerOpen();
    currentSocket().triggerMessage(SCORE_UPDATE);
    expect(listener).toHaveBeenCalledWith(SCORE_UPDATE);
    off();
  });

  it('ignores non-score_update messages and malformed JSON', () => {
    const listener = vi.fn();
    websocketManager.onMessage(listener);
    websocketManager.subscribe(1);
    currentSocket().triggerOpen();
    currentSocket().triggerMessage({ type: 'something_else' });
    currentSocket().triggerMessage('not-an-object');
    // Malformed frame — manager parses event.data; a string here parses fine
    // but isScoreUpdate rejects it.
    expect(listener).not.toHaveBeenCalled();
  });

  it('emits state changes to onStateChange listeners', () => {
    const listener = vi.fn();
    websocketManager.onStateChange(listener);
    // Initial state immediately fired on subscribe.
    expect(listener).toHaveBeenCalledWith('CLOSED');
    listener.mockClear();

    websocketManager.subscribe(1);
    expect(listener).toHaveBeenCalledWith('CONNECTING');

    currentSocket().triggerOpen();
    expect(listener).toHaveBeenCalledWith('OPEN');
  });

  it('subscribe is idempotent and does not double-send', () => {
    websocketManager.subscribe(1);
    currentSocket().triggerOpen();
    currentSocket().sent.length = 0;
    websocketManager.subscribe(1); // dup
    expect(currentSocket().sent).toEqual([]);
  });

  it('unsubscribe sends the message and removes the gamePk from tracking', () => {
    websocketManager.subscribe(1);
    currentSocket().triggerOpen();
    currentSocket().sent.length = 0;
    websocketManager.unsubscribe(1);
    const sent = currentSocket().sent.map((s) => JSON.parse(s));
    expect(sent).toEqual([{ action: 'unsubscribe', game_pk: 1 }]);

    // After a reconnect, gamePk 1 must NOT be re-subscribed.
    currentSocket().triggerClose();
    vi.advanceTimersByTime(1000);
    const second = currentSocket();
    second.triggerOpen();
    expect(second.sent).toEqual([]);
  });
});
