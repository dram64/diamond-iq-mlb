# ADR 011 — Real-time streaming pipeline (DynamoDB Streams → WebSocket fan-out)

## Status
Accepted

## Context
The frontend renders live MLB scoreboard data via TanStack Query
polling at 30-60 s intervals. That's fine for a static page reload
but feels stale during real games — a viewer watching a 1-1 tie in
the bottom of the 9th sees the score-changing hit a half-minute
late. The Option-4 scope expansion adds a real-time push path so
score changes propagate sub-second, without replacing the polling
behavior.

Eight things had to be settled before this could ship:

1. Stream source — DynamoDB Streams vs Kinesis vs eventbridge-pipes.
2. Fan-out transport — API Gateway WebSocket API vs Pinpoint vs SQS.
3. Polling: replace it, or augment it?
4. Authentication on the WebSocket handshake.
5. Whether to put WAF in front of the WebSocket endpoint.
6. Message ordering semantics for client bursts.
7. Stream-trigger batching window — latency vs invocation count.
8. Subscription cardinality — one game per connection vs many.

## Decision

### 1. DynamoDB Streams as the source

The games table already exists and has been emitting MODIFY events
on every ingest tick. Enabling Streams with `NEW_AND_OLD_IMAGES` is
a flag flip plus stream-arn output; the data path is already
populated. No additional ingest cost. No Kinesis shard cost.

For our portfolio scale (2 shards × $11/mo = $22/mo for Kinesis) the
saving is meaningful and Streams' delivery guarantees (at-least-once,
in-order per partition key) are sufficient for "push score updates."

### 2. API Gateway WebSocket API as the fan-out transport

API Gateway WebSocket gives us a managed connection registry, a
`PostToConnection` API for pushing to specific clients, and a
`$connect/$disconnect/$default` route model that pairs naturally with
a small Lambda per route.

Pinpoint and SQS were considered — both rejected. Pinpoint targets
mobile push (APNs/FCM) and is overkill for a browser. SQS doesn't
hold WebSocket connections; we'd still need API Gateway for that
and the fan-out logic would just live elsewhere.

### 3. Augment polling, don't replace

The frontend's existing `useGame` hook polls every 30 seconds. The
new `useGameSubscription` hook reconciles incoming WebSocket
messages directly into the TanStack Query cache via
`setQueriesData`. Three benefits:

- **Resilience.** A laptop sleep, a NAT timeout, or a transient
  CloudFront-edge issue would otherwise leave the user stuck at
  whatever score the WebSocket last saw. With polling running, the
  next 30-second refetch corrects everything; the WebSocket
  reconnects in the background.
- **No cache races.** Polling and push converge on the same
  TanStack Query cache. WebSocket messages mutate it; polling
  refetches and writes the same shape. No tug-of-war.
- **No regression risk.** If the entire WebSocket layer is
  removed, the app keeps working at polling speed. The push is
  pure-acceleration.

### 4. Unauthenticated `$connect` for v1

The WebSocket exposes the same data the public HTTP API already
exposes (game scores, statuses, linescores). There is no PII, no
auth-required content, and no write path. Adding a Cognito User Pool
or a Lambda authorizer just to gate access to public data adds
operational overhead without a threat-model improvement.

API Gateway's per-account WebSocket throttling (100 connections/sec
default) caps abuse-from-anonymous to a known floor. If we later
ship a per-user feature (alerts, favorites), `$connect` flips to
authenticated and existing clients reconnect through the new path —
not a breaking change because the server-side connection
cookie/token would be a new concept, not a replacement for an
existing one.

### 5. WebSocket NOT fronted by WAF in v1

WAFv2 supports WebSocket through CloudFront, but our existing
CloudFront distribution is configured for the HTTPS API origin only.
Adding WebSocket support means either:

- a new CloudFront distribution scoped to the WebSocket origin
  (extra config + extra DNS), or
- a path-based behavior on the existing distribution that proxies
  `/ws/*` to the WebSocket origin, with the implicit constraint that
  the frontend constructs `wss://<our-cloudfront>/ws/...` URLs
  (changes the frontend's `VITE_WS_URL` shape).

The threat-model justification for deferring this: data exposure
through the WebSocket is identical to the already-WAF-protected
HTTP API. A bot scraping our scoreboard via WebSocket gets the same
data as a bot scraping the HTTP API; the WAF rate-limits we wrote
for `/scoreboard/today` would need to be replicated for the
WebSocket origin to actually mean anything.

Future polish item — documented as a known follow-up rather than a
silently accepted gap.

### 6. Message ordering NOT guaranteed for client bursts

API Gateway WebSocket → Lambda integration is asynchronous: each
incoming message becomes its own Lambda invocation. AWS does not
guarantee that two messages from the same client process in the
order they were sent. We observed this in the e2e test for commit
2: three back-to-back messages (subscribe, subscribe, unsubscribe)
processed out of order, leaving the unsubscribed game still in the
table.

With realistic user pacing (≥500 ms between messages, e.g., a
button click that opens a panel) the race doesn't fire. Three
remediation paths were considered:

- **Client-side serialization.** The frontend awaits a server ack
  before sending the next message. Adds round-trip cost and
  requires the server to send acks (which it currently doesn't).
- **Server-side serialization.** Replace the API Gateway → Lambda
  integration with API Gateway → SQS-FIFO → Lambda. Adds an SQS
  queue per connection key (or a single queue with FIFO grouping).
  Significant complexity for portfolio scale.
- **Accept and document.** Real users don't burst messages
  microseconds apart; if a future feature needs ordering, the
  client can debounce.

We chose the third option: accept and document. The runbook
includes a debounce snippet for downstream developers who hit
this.

### 7. `maximum_batching_window_in_seconds = 1`

DynamoDB Streams batches records before invoking the consumer
Lambda. Lower window = lower latency but more invocations. Higher
window = fewer invocations but higher perceived latency.

Empirically, our end-to-end push latency (DynamoDB UpdateItem →
WebSocket frame) measures 0.7-0.9 s with `window=1`. Setting it to
0 would cut ~500 ms but multiply invocation cost by ~5-10×. Setting
it higher than 1 starts to feel slow on the rendered UI.

`parallelization_factor = 10` and
`bisect_batch_on_function_error = true` are also set: 10 concurrent
Lambda instances per shard so a single slow record doesn't stall
the queue, and bisect-on-error so a poison record halves the batch
on retry instead of stalling the whole shard.

### 8. Many subscriptions per connection via composite SK schema

The connections-table schema has:

```
PK: connection_id    SK: META
PK: connection_id    SK: GAME#<game_pk>
GSI by-game:  PK: game_pk_str    SK: connection_id
```

A subscribe writes one `GAME#<pk>` row. An unsubscribe deletes it.
On `$disconnect`, the handler queries every row for the connection
and batch-deletes them.

This shape lets the stream-processor query the by-game GSI in O(1)
to find subscribers and lets a single connection watch the entire
scoreboard at the cost of one row per game. The alternative
(one-game-per-connection with the game_pk as a single META
attribute) would have forced the frontend to open 15 sockets to
watch a 15-game slate.

## Consequences

### Positive
- **Sub-second perceived latency.** End-to-end UpdateItem → frame
  arrives in ~0.7-0.9 s in the production environment.
- **No regression risk.** Polling is unchanged; the WebSocket
  layer is purely additive. If anything in the pipeline breaks,
  users see the same 30-second-stale data they had before.
- **One WebSocket per browser tab.** The singleton manager
  multiplexes every page that calls `useGameSubscription` over
  the same connection, with one subscribe per game.
- **Stream is at-least-once, in-order per game.** DynamoDB Streams
  partitions by item key — every MODIFY for a single game lands
  on the same shard in order, so two close-together score updates
  are pushed in the order they happened.
- **Idempotent reconnect.** A laptop sleep → wake cycle reopens
  the WebSocket and re-sends every tracked subscribe; the user
  sees no loss.
- **Cheap.** ~$1-2/month additional at portfolio scale.

### Negative
- **No message ordering for client bursts.** Documented in the
  runbook with a client-debounce remediation pattern.
- **No WAF in front of the WebSocket.** Documented as a future
  polish item; data exposure threat-model is unchanged from the
  HTTP API.
- **WebSocket disconnect storms could overwhelm reconnect logic.**
  The exponential backoff caps at 30 s, but a thousand simultaneous
  reconnects from a network outage would still take a minute or
  two to settle. Not relevant at portfolio scale; a future polish
  item if traffic ever justifies it.
- **DynamoDB Streams adds a 6-12 hour stream retention cost** —
  retention is fixed at 24 h and cannot be tuned. Free tier covers
  our volume but the choice locks us in to that retention window.

### Operational notes
- The first deploy hit four IAM gaps in sequence:
  - `dynamodb:CreateTable` on the connections table — IAM
    propagation race (already-handled pattern).
  - Account-level `apigatewayv2:UpdateAccount` for the WebSocket
    stage's CloudWatch Logs role — prerequisite, not a race.
  - `lambda:TagResource` on `event-source-mapping:*` ARN class —
    AWS provider 5.x default-tag behavior touches a different
    ARN shape than the function-level grant.
  - One more IAM propagation race after `lambda:TagResource`
    was added.
- All four resolved in the established self-heal pattern: diagnose,
  grant, retrigger.
- Known unresolved: WAF Web ACL `update in-place` shows on every
  Terraform plan as drift. Functional impact is nil — the in-place
  update reapplies identical rules. Documented in commit messages
  as provider-level noise.

## Alternatives considered

### Stream source
- **Kinesis Data Streams.** ~$11/month per shard at portfolio
  scale plus producer-side retry complexity. Rejected on cost.
- **EventBridge Pipes.** Higher abstraction, more ops surface,
  same end-to-end shape. Rejected — DynamoDB Streams + Lambda is
  AWS's documented "easy mode" for this pattern.
- **Polling-only at higher frequency.** At 5-second polls per
  client × N concurrent users, we'd hit our DynamoDB read
  capacity cliff well before 100 users. Rejected.

### Fan-out transport
- **Pinpoint mobile push.** Wrong shape for a browser page.
  Rejected.
- **SQS fan-out per connection.** Significantly heavier
  infrastructure for what is effectively "send a JSON blob to a
  TCP socket." Rejected.
- **Server-Sent Events (SSE).** Workable, but API Gateway HTTP
  API doesn't support SSE natively (it would need a long-poll
  shim Lambda or a different ingress). Rejected.

### Polling story
- **Replace polling.** Lose resilience. Rejected.
- **Disable polling when WebSocket connects, re-enable on
  disconnect.** Race-prone at the boundary; for portfolio scale
  the savings are negligible.

### WebSocket auth
- **Cognito user pools at $connect.** Adds a user-pool
  dependency, sign-up flow, token rotation, and a Cognito JWT
  authorizer Lambda. Out of scope for v1.
- **Lambda authorizer with API key.** Simpler than Cognito but
  the API-key concept is meaningless when the data is public.
- **No auth.** Chosen.

### Ordering
- **SQS-FIFO for serialization.** Defended above.
- **WebSocket binary frames with sequence numbers + client
  reorder buffer.** Over-engineered for portfolio scale.
- **Accept and document.** Chosen.

### Subscription cardinality
- **One game per connection.** Watcher of a 15-game scoreboard
  needs 15 sockets. Rejected on cost-of-handshake.
- **Single attribute holding a NumberSet of subscribed games.**
  Can't query by-game without a scan. Rejected.
- **Composite SK with per-game subscription rows.** Chosen.

### Cost (~$1-2/month additional)

| Component | Monthly |
|---|---|
| DynamoDB Streams | included with table |
| Connections table (PAY_PER_REQUEST) | <$0.10 |
| 4 new Lambdas (connect, disconnect, default, stream-processor) | <$0.50 |
| API Gateway WebSocket connection minutes (~5 concurrent × 1h × 30 days) | <$0.01 |
| API Gateway WebSocket messages (~600 K msgs/month) | ~$0.60 |
| CloudWatch Logs for new functions | <$0.20 |
| **Total** | **~$1.50** |

## Future polish

- **WebSocket auth.** Cognito user pool or a Lambda authorizer if
  abuse appears or if a per-user feature lands.
- **WAF protection on WebSocket.** CloudFront fronting via
  path-based behavior on the existing distribution.
- **Client-side message debouncing.** Wrap `subscribe`/`unsubscribe`
  in a 200-ms debouncer if a UI change introduces burst patterns.
- **Pinpoint or SQS fan-out for >1000 concurrent connections.**
  Not relevant at portfolio scale; documented as a scale-up path.
- **Frontend cache update for the scoreboard view.** The
  `useScoreboard` cache (`['scoreboard', date]`) currently doesn't
  receive WebSocket updates — only the per-game `['game', pk, date]`
  cache does. Live updates appear on `/live/<gameId>` instantly,
  but the home-page scoreboard cards still show on the polling
  cadence. A small `useScoreboard` extension to listen for
  same-day score_update messages and patch the appropriate game
  in the scoreboard array would close this gap.
