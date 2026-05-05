/**
 * WebSocket client for the real-time score-update pipeline.
 *
 * Module-level singleton — every component that calls useGameSubscription
 * shares one underlying WebSocket connection to the API Gateway WebSocket
 * API. The manager handles:
 *
 *   - lazy connect on first subscribe
 *   - reconnect with exponential backoff (1s, 2s, 4s, 8s, 16s, capped at 30s)
 *   - track of the subscribed game_pk set so reconnects re-send subscribes
 *   - typed message dispatch to listeners
 *   - connection-state changes broadcast to UI listeners (status dot)
 *
 * Lifecycle for the host page:
 *   - useGameSubscription calls .connect() on mount → manager opens if closed
 *   - .subscribe(gamePk) sends {action,game_pk}; if not yet OPEN, queues
 *     the subscribe and flushes on open
 *   - .unsubscribe(gamePk) is the inverse; if no subscriptions remain,
 *     the connection stays open (cheap; closes on tab close anyway)
 *   - WebSocket close triggers reconnect unless .disconnect() was called
 *     manually
 */

import { WS_URL } from './env';
import type { ApiScoreUpdateMessage } from '@/types/api';

export type ConnectionState = 'CONNECTING' | 'OPEN' | 'CLOSING' | 'CLOSED';

const RECONNECT_DELAYS_MS = [1_000, 2_000, 4_000, 8_000, 16_000, 30_000] as const;

/** Cap reconnect attempts at the longest delay; never escalate beyond it. */
function backoffMs(attempt: number): number {
  const idx = Math.min(attempt, RECONNECT_DELAYS_MS.length - 1);
  return RECONNECT_DELAYS_MS[idx]!;
}

type MessageListener = (msg: ApiScoreUpdateMessage) => void;
type StateListener = (state: ConnectionState) => void;
type Unsubscribe = () => void;

interface Outbound {
  action: 'subscribe' | 'unsubscribe';
  game_pk: number;
}

class WebSocketManager {
  private ws: WebSocket | null = null;
  private state: ConnectionState = 'CLOSED';
  private subscriptions = new Set<number>();
  /** Pending outbound messages waiting for OPEN. Emptied on `flush`. */
  private outbox: Outbound[] = [];
  private messageListeners = new Set<MessageListener>();
  private stateListeners = new Set<StateListener>();

  private reconnectAttempt = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private wantConnected = false;

  /** Lazily open the WebSocket. Idempotent. */
  connect(): void {
    this.wantConnected = true;
    if (this.state === 'OPEN' || this.state === 'CONNECTING') return;
    this.openWebSocket();
  }

  /** Manually close the connection and clear all subscriptions. */
  disconnect(): void {
    this.wantConnected = false;
    if (this.reconnectTimer != null) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.subscriptions.clear();
    this.outbox = [];
    if (this.ws) {
      this.setState('CLOSING');
      this.ws.close();
      this.ws = null;
    }
    this.setState('CLOSED');
  }

  subscribe(gamePk: number): void {
    if (this.subscriptions.has(gamePk)) return;
    this.subscriptions.add(gamePk);
    this.send({ action: 'subscribe', game_pk: gamePk });
  }

  unsubscribe(gamePk: number): void {
    if (!this.subscriptions.has(gamePk)) return;
    this.subscriptions.delete(gamePk);
    this.send({ action: 'unsubscribe', game_pk: gamePk });
  }

  /** Subscribe to incoming score_update messages. Returns an unsubscriber. */
  onMessage(listener: MessageListener): Unsubscribe {
    this.messageListeners.add(listener);
    return () => this.messageListeners.delete(listener);
  }

  /** Subscribe to connection-state changes (used by the status indicator). */
  onStateChange(listener: StateListener): Unsubscribe {
    this.stateListeners.add(listener);
    // Emit current state immediately so callers don't render "unknown" first.
    listener(this.state);
    return () => this.stateListeners.delete(listener);
  }

  getState(): ConnectionState {
    return this.state;
  }

  // ── internals ──────────────────────────────────────────────────────

  private setState(state: ConnectionState): void {
    if (this.state === state) return;
    this.state = state;
    for (const l of this.stateListeners) l(state);
  }

  private openWebSocket(): void {
    this.setState('CONNECTING');
    let ws: WebSocket;
    try {
      ws = new WebSocket(WS_URL);
    } catch {
      this.setState('CLOSED');
      this.scheduleReconnect();
      return;
    }
    this.ws = ws;

    ws.onopen = () => {
      this.reconnectAttempt = 0;
      this.setState('OPEN');
      // Replace the outbox with the canonical set of tracked subscribes —
      // anything queued via send() while CONNECTING is already represented
      // in this.subscriptions, so re-iterating from the set is the single
      // source of truth and avoids duplicate-subscribe sends.
      this.outbox = Array.from(this.subscriptions, (pk) => ({
        action: 'subscribe' as const,
        game_pk: pk,
      }));
      this.flush();
    };

    ws.onmessage = (event) => {
      const data = typeof event.data === 'string' ? event.data : '';
      if (!data) return;
      let parsed: unknown;
      try {
        parsed = JSON.parse(data);
      } catch {
        return; // malformed frame — server-side bug, not our problem
      }
      if (!isScoreUpdate(parsed)) return;
      for (const l of this.messageListeners) l(parsed);
    };

    ws.onclose = () => {
      this.ws = null;
      this.setState('CLOSED');
      if (this.wantConnected) this.scheduleReconnect();
    };

    ws.onerror = () => {
      // Real connection errors come through as onclose right after; let that
      // path handle reconnect. Just log; no need to double-trigger.
    };
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer != null) return;
    const delay = backoffMs(this.reconnectAttempt);
    this.reconnectAttempt += 1;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      if (this.wantConnected) this.openWebSocket();
    }, delay);
  }

  private send(msg: Outbound): void {
    if (this.state === 'OPEN' && this.ws) {
      this.ws.send(JSON.stringify(msg));
    } else {
      this.outbox.push(msg);
      if (this.state === 'CLOSED') this.connect();
    }
  }

  private flush(): void {
    if (!this.ws || this.state !== 'OPEN') return;
    while (this.outbox.length > 0) {
      const msg = this.outbox.shift()!;
      this.ws.send(JSON.stringify(msg));
    }
  }
}

function isScoreUpdate(value: unknown): value is ApiScoreUpdateMessage {
  return (
    typeof value === 'object' &&
    value !== null &&
    (value as { type?: unknown }).type === 'score_update' &&
    typeof (value as { game_pk?: unknown }).game_pk === 'number'
  );
}

export const websocketManager = new WebSocketManager();
