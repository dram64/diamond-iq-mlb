/**
 * Subscribe to real-time updates for a single game.
 *
 * On mount, opens a WebSocket (if not already open) and sends a `subscribe`
 * message for `gamePk`. On unmount, sends an `unsubscribe`. Incoming
 * score_update messages for this gamePk are reconciled into the TanStack
 * Query cache via setQueryData on the same key shape useGame uses
 * (`['game', gamePk, date]`); the next refetch sees no diff and is a no-op.
 *
 * This hook AUGMENTS useGame's polling, it doesn't replace it. If the
 * WebSocket disconnects, the polling loop continues serving as a backstop
 * until the reconnect handshake completes.
 *
 * The returned `connectionState` lets the host UI render a status indicator.
 */

import { useEffect, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';

import { applyDiff } from '@/lib/applyDiff';
import { websocketManager, type ConnectionState } from '@/lib/websocket';
import type { ApiScoreUpdateMessage, GameDetailResponse } from '@/types/api';

export interface UseGameSubscriptionResult {
  connectionState: ConnectionState;
}

export function useGameSubscription(
  gamePk: number | undefined,
): UseGameSubscriptionResult {
  const queryClient = useQueryClient();
  const [connectionState, setConnectionState] = useState<ConnectionState>(
    websocketManager.getState(),
  );

  // State subscription is independent of gamePk — the status indicator
  // wants to render from the moment the hook mounts.
  useEffect(() => {
    return websocketManager.onStateChange(setConnectionState);
  }, []);

  // Subscribe / unsubscribe lifecycle.
  useEffect(() => {
    if (typeof gamePk !== 'number' || !Number.isFinite(gamePk)) return;
    websocketManager.connect();
    websocketManager.subscribe(gamePk);
    return () => websocketManager.unsubscribe(gamePk);
  }, [gamePk]);

  // Inbound message → cache reconciliation.
  useEffect(() => {
    if (typeof gamePk !== 'number' || !Number.isFinite(gamePk)) return;
    const off = websocketManager.onMessage((msg: ApiScoreUpdateMessage) => {
      if (msg.game_pk !== gamePk) return;
      // useGame's query key is ['game', gamePk, date]; we don't know the
      // date here so target every entry whose first two key segments match.
      queryClient.setQueriesData<GameDetailResponse>(
        {
          predicate: (query) => {
            const [a, b] = query.queryKey as readonly unknown[];
            return a === 'game' && b === gamePk;
          },
        },
        (old) => {
          if (!old) return old;
          return { ...old, game: applyDiff(old.game, msg.changes) };
        },
      );
    });
    return off;
  }, [gamePk, queryClient]);

  return { connectionState };
}
