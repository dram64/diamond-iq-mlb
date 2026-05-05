import type { ConnectionState } from '@/lib/websocket';

interface WebSocketStatusDotProps {
  state: ConnectionState;
}

/**
 * Tiny inline indicator for the real-time WebSocket pipeline.
 *
 *   OPEN        green   real-time push active
 *   CONNECTING  yellow  reconnecting; polling still serves as backstop
 *   CLOSING     yellow  graceful close in flight
 *   CLOSED      gray    polling-only mode
 *
 * Tooltip on hover documents the state for non-technical reviewers.
 */
export function WebSocketStatusDot({ state }: WebSocketStatusDotProps) {
  const { color, label, title } = describe(state);
  return (
    <span
      className="inline-flex items-center gap-1.5 text-[10.5px] font-semibold uppercase tracking-[0.06em] text-paper-4"
      title={title}
    >
      <span
        aria-hidden="true"
        className="inline-block h-2 w-2 rounded-full"
        style={{ background: color }}
      />
      <span>{label}</span>
    </span>
  );
}

function describe(state: ConnectionState): {
  color: string;
  label: string;
  title: string;
} {
  switch (state) {
    case 'OPEN':
      return {
        color: '#16a34a',
        label: 'Live',
        title: 'WebSocket connected — score updates push in real time.',
      };
    case 'CONNECTING':
      return {
        color: '#eab308',
        label: 'Connecting',
        title: 'WebSocket reconnecting — polling continues as backstop until it lands.',
      };
    case 'CLOSING':
      return {
        color: '#eab308',
        label: 'Closing',
        title: 'WebSocket closing.',
      };
    case 'CLOSED':
    default:
      return {
        color: '#9ca3af',
        label: 'Polling',
        title: 'WebSocket disconnected — falling back to polling refresh.',
      };
  }
}
