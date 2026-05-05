# ADR 012 — Player and pitch-event data architecture

## Status
Accepted (design only; implementation deferred to Option 5 Phase 5B+).

## Context
Four sections of the home page render mock data and carry "Demo data"
badges:

- `LeaderCard` — batting and pitching leaders, plus standings.
- `HardestHitChart` — top hardest-hit balls of the day.
- `CompareStrip` — two-player side-by-side comparison.
- `TeamGridCard` — 8-team summary cards.

To remove those badges we need real player metadata, season stats,
team standings, and pitch-event data. The MLB Stats API exposes all
of it for free (no auth, no rate-limit ceremony beyond ~100 req/min/IP
common-courtesy). Six things had to be settled to commit to an
architecture before writing any code:

1. **Single-table or multi-table?** Existing project pattern is
   single-table on `diamond-iq-games`. Adding 5+ new tables would
   double the operational surface (Terraform, IAM, TTL, alarms).
2. **Schema shape — PK/SK per entity, GSI strategy.** Determines
   read efficiency for every dashboard component.
3. **Ingest cadence — daily batch vs event-triggered.** Batch is
   simpler; event-triggered scales better but adds plumbing.
4. **Computed metrics scope — trust the API or derive locally?**
   The portfolio bar is "we know what these mean," not "we beat
   Fangraphs."
5. **Pitch-level retention scope — every pitch, or only the
   hardest-hit subset?** Storage cost vs feature flexibility.
6. **Cross-season query support — committed to in v1, or deferred?**
   PK shape decision; cheap to bake in now, expensive to retrofit.

The full design lives in [docs/option5-design.md](../option5-design.md).
This ADR records the architectural commitments.

## Decision

### 1. Single-table extension of `diamond-iq-games`

All new entity types share the games table. Existing `GAME#<date>` and
`CONTENT#<date>` partitions are unaffected. The new partitions
(`PLAYER#GLOBAL`, `ROSTER#<season>#<teamId>`, `STATS#<season>#<group>`,
`STANDINGS#<season>`, `LEADERBOARD#<season>#<group>#<stat>`,
`HITS#<date>`) coexist on the same hash space without collisions
because the prefix discriminates by entity type.

This avoids ~5 new Terraform table resources, ~5 new IAM scopes,
and ~5 new TTL configs. It also means every Lambda that needs
reads across entity types (e.g., a player profile page that wants
metadata + current-season stats) can do them with a single
DynamoDB connection.

### 2. Pre-computed leaderboard snapshots, no GSI on stats

Two viable patterns for "top N players by stat":

- **Sparse GSI on the stats table** — query the GSI with
  `PK=STATS_LEADER#<season>#<group>#<stat>` and `Limit=N`.
  Real-time-ish but adds GSI write cost to every stats write.
- **Pre-computed leaderboard snapshots** — a daily Lambda reads
  the stats partition, sorts in-memory, writes top-50 rows to
  `LEADERBOARD#<season>#<group>#<stat>` with rank in the SK. Reads
  are pure Query with no filtering.

We picked **pre-compute** for v1. Rationale:

- Leaderboards are rendered once per dashboard page load by every
  user. A stale-by-up-to-24h leaderboard is acceptable for a
  portfolio analytics product. Live recomputation isn't a
  user-visible benefit.
- The daily compute Lambda is ~10 lines of pandas-free Python
  reading 230 rows and writing 500 — cheap.
- No GSI write multiplier on the hot ingest path.

If a future product need surfaces a real-time leaderboard
requirement, we'd add the GSI then.

### 3. Daily-batch ingest with three Lambdas

Three new Lambdas, each driven by EventBridge cron:

- **`ingest-players`** at 14:00 UTC — fetches teams + rosters +
  player metadata.
- **`ingest-stats`** at 14:30 UTC — fetches season stats for
  every qualified player; computes wOBA / OPS+ / FIP locally.
- **`compute-leaderboards`** at 15:00 UTC — sorts and snapshots
  the top-50 per stat.

Plus an extension to the existing ingest pipeline:

- A `extract-hits` Lambda triggered by DynamoDB Streams when a
  game's status transitions from `live` to `final`, walking
  `feed/live` for that game and writing hits with
  `launchSpeed > 95 mph` into `HITS#<date>`.

The batch cadence is intentionally aligned with the existing daily
content-generation Lambda (15-17 UTC window). Operationally it's
one wave per day, not a constant trickle.

### 4. Trust API direct stats; compute the wOBA/OPS+/FIP trio

The MLB Stats API directly provides every common stat
(`avg`, `obp`, `slg`, `ops`, `homeRuns`, `era`, `whip`, etc.). We
trust the upstream values. We compute three "advanced" metrics
ourselves: **wOBA** (linear-weighted on-base average),
**OPS+** (park-and-league-adjusted OPS), and **FIP**
(fielding-independent pitching).

The three were chosen because: (a) they are recognizable to
anyone looking at the project as a portfolio, (b) the formulas
are straightforward and require only primitives the API already
returns, and (c) computing them locally demonstrates we
understand the math, not just the API surface.

We deferred xwOBA, BABIP-against, ZiPS-style projections, and
park-adjusted SLG — all are interesting but require Statcast-grade
data or third-party model inputs we'd have to source elsewhere.

### 5. Hardest-hit-only pitch-event storage; deferred full retention

Storing every pitch event for every game is ~600k items/season.
Storing only events with `launchSpeed > 95.0 mph` (the threshold
MLB uses for "hard-hit") is ~50 events/day, ~9k/season. The
`HardestHitChart` only needs the latter.

Deferred: a `PITCHES#<season>#<pitcherId>` partition and the ingest
path to populate it. Documented as a Phase 5C+ option contingent on
real product need.

### 6. Season prefix in every PK; cross-season queries supported

Every entity that has a season scope (rosters, stats, standings,
leaderboards) embeds `<season>` in its PK. The cost is one extra
partition-key segment; the benefit is "compare 2026 to 2024" reads
become a `Query PK=STATS#2024#hitting`-style call instead of a
new schema migration.

The alternative (assume current season everywhere, retrofit when
asked for historical) would have made historical queries
require either a backfill sweep or a second table. Both are
worse than baking the season in now.

## Consequences

### Positive
- **One table, one IAM scope, one TTL config.** Operational
  surface stays where it is.
- **Single-Query reads for every dashboard component.** No fan-out,
  no client-side joins, no filtered scans.
- **Seasonal data is naturally partitioned.** Off-season cleanup
  is a date-prefix delete; cross-season comparison is a season
  swap.
- **Computed-stat trio is auditable.** Every wOBA/OPS+/FIP value
  in the table can be derived from primitives also stored in the
  table; reviewers can verify by hand.
- **No GSI on the high-write stats partition.** Write cost stays
  flat as the active player count grows.
- **Hardest-hit pitch storage is small and self-cleans via TTL.**
  No off-platform analytics tooling needed.

### Negative
- **Leaderboards stale by up to 24 hours.** Real-time leaderboard
  recomputation requires a future-phase GSI add.
- **Three new Lambdas plus one stream-triggered extension.** Each
  with its own log group, IAM policy, error alarm. ~10 minutes of
  Terraform per Lambda, well-trodden.
- **MLB API rate limit becomes a soft constraint at 10× scale.**
  Documented in the design doc; mitigation is splitting fetches
  across a wider window or using the `?personIds=1,2,...` bulk
  endpoint where supported.
- **No source-of-truth for league constants** (`lgOBP`, `cFIP`).
  Either compute by aggregating qualified-player totals daily, or
  hardcode an approximation per season. Implementation Phase 5B
  picks one.
- **`war` field inconsistency** in the MLB API response. The
  computed-stats trio doesn't depend on it, but `LeaderCard`
  currently renders WAR — Phase 5B verifies coverage before
  shipping.

### Operational notes
- Adding new partition prefixes to the existing single table does
  not require a Terraform migration — DynamoDB doesn't enforce
  schema. The Lambda IAM scope (`dynamodb:PutItem` on the table
  ARN) covers all new entity writes without policy changes.
- The `extract-hits` Lambda follows the streaming-pipeline pattern
  established in Option 4 (DynamoDB Streams trigger,
  `bisect_batch_on_function_error`, parallelization_factor=10).
  Same-shape implementation; only the diff function and the write
  target differ.
- Pre-existing `diamond-iq-stream-processor` Lambda is unchanged
  — `extract-hits` is a separate consumer of the same stream so
  the WebSocket fan-out and the hit extraction can fail
  independently.

## Alternatives considered

### Schema

- **Multi-table — one table per entity type.** Cleaner mental
  model but ~5× operational surface. Rejected for portfolio
  ergonomics.
- **Single-table with a single shared partition key shape and
  no entity prefix.** SK collisions become possible
  (a `STATS#<personId>` and a `ROSTER#<personId>` would both want
  to live under the same player). Rejected.

### Leaderboard read pattern

- **Sparse GSI for real-time top-N.** Adds write cost on every
  stats refresh × every leadable stat. Rejected for v1.
- **Compute on read in the API Lambda.** Simple but every page
  load triggers a Query of all qualified players' stats (~150
  rows × 5 KB ≈ 1 MB) and sorts in-memory before returning.
  Cold start latency unacceptable. Rejected.

### Ingest cadence

- **Per-game-final triggered.** Better-than-daily freshness but
  the leaderboard depends on the full league's stats, so a
  per-game trigger would re-run the leaderboard compute 15
  times/day. Marginal benefit; rejected.
- **Continuous polling at 1-minute intervals like the games
  ingest.** 1500 active players × 60 polls/hour = unsustainable
  and against MLB's effective rate limit. Rejected.

### Computed-metric scope

- **No locally-computed stats; just render the API direct
  values.** Loses the "we understand sabermetrics" portfolio
  signal. Rejected.
- **Full Fangraphs-grade derived stat suite (xwOBA, ZiPS, etc.).**
  Multiple-week project on its own; out of scope for v1.

### Pitch-level retention

- **Every pitch every game.** ~600k items/season. Storage cost
  is fine; query patterns are unclear without a feature need.
  Rejected — premature.
- **No pitch-level data at all.** Can't satisfy `HardestHitChart`.
  Rejected.
- **Hard-hit only (>95 mph).** Compromise; matches the only known
  consumer.

### Season prefix

- **Implicit current-season; no prefix.** Saves ~6 chars per PK,
  costs a future migration when historical queries land. Rejected.
- **Calendar year prefix at every level (PK + SK).** Bloats SKs
  for marginal benefit; PK-only is the cleaner location.

## Forward references

- Implementation begins in **Phase 5B** against the schema and
  ingest plan in [docs/option5-design.md](../option5-design.md).
- Open questions list in section (g) of the design doc must be
  resolved or formally deferred before Phase 5B PRs land.
- This ADR is the contract; subsequent commits in Option 5 should
  link back here when they instantiate one of the entity types
  or computed metrics.

## Amendment — Phase 5B implementation decisions

Phase 5B ships the `ingest-players` Lambda. Five decisions deviated
from or refined the original ADR; recording them here so the ADR
matches what's deployed.

### 1. WAR dropped from the schema entirely

The "Negative" bullet above flagged WAR coverage as a Phase 5B
verification item. **Outcome:** verified live against `personId=592450`
(Aaron Judge) in 2026 — the MLB Stats API does not expose `war` on
`/people/{id}` nor in the `stats(group=hitting,type=season)` hydrate.
The field is `null` at the top level and absent from `splits[].stat`.

We removed WAR from the player metadata projection rather than ship
a permanently-null field. The 8 stored metadata attributes are:
`person_id`, `full_name`, `primary_number` (when present),
`current_age`, `height`, `weight`, `bat_side`, `pitch_hand`,
`primary_position_abbr`. `LeaderCard`'s WAR row will need to source
from a different upstream (Fangraphs scrape, manual data entry, or
the Phase 5C+ derived-metrics pipeline) — out of Phase 5B scope.

### 2. Two cron schedules, single Lambda, mode parameter

ADR 012 specified `ingest-players at 14:00 UTC` as a single rule.
Phase 5B splits the work across two EventBridge schedules driving
the same function:

- `rate(7 days)` with `{"mode": "full"}` — refreshes player
  metadata (changes rarely; weekly is enough).
- `cron(0 12 * * ? *)` with `{"mode": "roster_only"}` — refreshes
  roster assignments (trades, call-ups; needs daily freshness).

The handler validates mode against `frozenset({"full", "roster_only"})`,
defaults to `"full"`, and branches on the bulk-people-fetch step.
Single Lambda over two because the deployment surface (IAM,
alarm wiring, log group) is shared and the branching is ~10 lines.

### 3. 50-ID batching with silent-drop log

The `/people?personIds=` bulk endpoint silently drops unknown IDs
(verified live: 1 bogus + 2 real returned HTTP 200 with 2 people).
Phase 5B chunks person IDs at `PEOPLE_BULK_BATCH_SIZE = 50`,
computes a requested-vs-returned diff per batch, and logs at INFO
when IDs are dropped. **Silent drops do not increment
`PlayersFailedCount`** — they're an upstream-data condition, not a
handler failure. A whole-batch fetch failure (HTTP 5xx after retry
exhaustion) does count toward `PlayersFailedCount` and is isolated
per-batch so other batches still run.

### 4. Daily-only invocations-zero alarm; weekly skipped

CloudWatch metric-alarm `period` caps at 86400 seconds (24 hours).
Setting an `Invocations <= 0 over 7 days` alarm requires a custom
metric-math expression and adds operational complexity for a
weekly schedule that is also covered indirectly by the
`Errors > 0` alarm (a missed cron emits no errors but also no
invocations — a 7-day silence would surface the next week
regardless). The runbook should call out manual weekly verification
during ops rotation; the alarm is intentionally absent.

### 5. Custom metrics under `DiamondIQ/Players`

Four metrics emitted via `cloudwatch:PutMetricData` scoped by
namespace condition: `PlayersIngestedCount`, `RostersIngestedCount`,
`TeamsFailedCount`, `PlayersFailedCount`. Emission is wrapped in
try/except — a metrics-API outage doesn't fail the Lambda. The
namespace is the IAM scope boundary (`cloudwatch:namespace`
condition key on the Statement), keeping the function unable to
write to other projects' namespaces.

## Amendment — Phase 5C implementation decisions

Phase 5C ships the `ingest-daily-stats` Lambda (per-game
`DAILYSTATS#<date>` rows + bulk-refreshed
`STATS#<season>#<group>` season records). Five decisions deviated
from or refined section 3 / section 4 of the original ADR.

### 1. Schedule API drives game discovery, not DynamoDB

ADR 012 § 3 implied the daily Lambda would query the games table
for yesterday's Final games. Phase 5C uses the MLB Stats API
schedule endpoint (`/api/v1/schedule?sportId=1&date=YYYY-MM-DD`)
filtered to `detailedState == "Final"` instead. Decoupling the
stats Lambda from `ingest-live-games`' write timing (and from the
existence of GAME rows for that date at all) makes the stats run
robust to upstream lag. Schedule API is also the canonical source
of truth for game status, including Suspended/Postponed/Cancelled,
which we filter out at the source.

### 2. Lightweight `/boxscore` endpoint, not `/feed/live`

`/api/v1/game/{gamePk}/boxscore` returns ~20-50 KB and contains
everything we need: per-player `stats.batting`, `stats.pitching`,
`seasonStats`, `jerseyNumber`, `position`, `parentTeamId`. The
full `/api/v1.1/game/{gamePk}/feed/live` payload is 100-500 KB and
includes plays, pitch-by-pitch, and other data we don't write in
Phase 5C. The boxscore endpoint is materially cheaper without
sacrificing any field we write.

### 3. Bulk season-stats endpoint for qualified players

ADR 012 § 4 implied per-player `/people/{id}/stats?stats=season`
calls (~250 calls) to refresh season records. Phase 5C uses the
bulk endpoint instead:

```
GET /api/v1/stats?stats=season&group=hitting&season=<year>&playerPool=Qualified&limit=200
GET /api/v1/stats?stats=season&group=pitching&season=<year>&playerPool=Qualified&limit=200
```

Two calls cover the entire qualified pool (~150 hitters + ~100
pitchers), each split returning `player.id`, `team.id`, and the
full stat object — directly mappable to `STATS#<season>#<group>`
rows. Verified live during Phase 5C planning.

Non-qualified players' season stats are populated via the
`seasonStats` block embedded in their per-game boxscore line,
which we write daily for every player who appeared. The bulk
`/stats?playerPool=Qualified` endpoint covers leaderboard
candidates. Net coverage is complete: qualified players get
refreshed via bulk endpoint daily, non-qualified players get
refreshed each time they appear in a game's boxscore. This is
cheaper and more current than per-player season fetches for
non-qualified players.

### 4. Daily 09:00 UTC cron, single mode

One EventBridge rule (`cron(0 9 * * ? *)`) drives the standard
daily run. 09:00 UTC = 02:00 PT, leaves a ~1-2h buffer after the
latest West Coast extra-inning finish. A second mode
`{"mode": "season_only"}` exists for manual backfills (skips the
boxscore fan-out, only refreshes the bulk season records); it has
no scheduled trigger.

The `ok = False` threshold is a failure ratio: if more than 50%
of the day's games failed (boxscore fetch error, processing
exception), the run reports failure. A small number of failed
boxscores (one suspended game's resumption, one MLB hiccup) is
not worth alarming.

### 5. Computed stats: `total_bases` and `k_bb_ratio` only

Per-game computed stats are scoped narrowly:
- `total_bases` = singles + 2·doubles + 3·triples + 4·HR
- `k_bb_ratio` = strikeouts / walks (omitted entirely when walks=0
  to avoid divide-by-zero placeholders)

The wOBA / OPS+ / FIP trio from ADR 012 § 4 is **deferred to
Phase 5D** because each requires league-wide constants (lgOBP,
park factors, cFIP) that we don't compute until the leaderboard
phase. Phase 5C ships the per-game primitives Phase 5D will
aggregate over.

### Alarms and metrics

Three CloudWatch alarms (errors, duration-near-timeout,
invocations-zero) routed to `diamond-iq-alerts`. Five custom
metrics under `DiamondIQ/DailyStats`: `GamesProcessed`,
`BattersIngested`, `PitchersIngested`, `SeasonStatsRefreshed`,
`GamesFailed`. Same try/except metric-emission pattern as 5B —
a metrics-API outage does not fail the Lambda.

## Amendment — Phase 5D implementation decisions

Phase 5D ships the `compute-advanced-stats` Lambda. Per-player
wOBA / OPS+ / FIP are written back to the existing
`STATS#<season>#<group>` records via UpdateItem (no overwrite of
upstream-authoritative fields). League means and the cFIP
constant are computed from our own qualified-player aggregates,
so the league-mean FIP equals the league-mean ERA by
construction — self-consistent without an external dependency.

### 1. Phase 5C ingest projection expanded

The original Phase 5C `_season_item` projected ~20 attributes —
sufficient for the dashboard, insufficient for wOBA / FIP inputs.
Phase 5D adds 8 fields to the hitter projection (`at_bats`,
`doubles`, `triples`, `walks`, `intentional_walks`,
`sacrifice_flies`, `hit_by_pitch`, `plate_appearances`) and 3 to
the pitcher projection (`walks`, `hit_by_pitch`, `earned_runs`).
The 5C handler change shipped first; one manual `season_only`
invocation backfilled the 259 existing records.

For pitcher records, MLB exposes HBP-given-up under the
`hitBatsmen` key (not `hitByPitch`, which on a pitcher's split
means something different in the API). We store under
`hit_by_pitch` so attribute naming is symmetric across record
groups; the semantic distinction is the record's group.

### 2. wOBA — Fangraphs Guts 2023 linear weights, hardcoded

```python
weights = {ubb: 0.69, hbp: 0.72, 1B: 0.89, 2B: 1.27, 3B: 1.62, HR: 2.10}
wOBA = (Σ weight·event) / (AB + BB - IBB + SF + HBP)
```

Source: `fangraphs.com/guts.aspx?type=cn`, year 2023. Weights
drift in the 3rd decimal across seasons; the 2023 published
constants are within 0.5% of more recent values and within
portfolio-grade tolerance. If a future season's drift becomes
load-bearing, override is a one-line change in `_WOBA_WEIGHTS`.

### 3. OPS+ — league-relative, no park adjustment (documented limitation)

```python
OPS+ = 100 · (OBP / lgOBP + SLG / lgSLG - 1)
lgOBP = mean(OBP across qualified hitters)
lgSLG = mean(SLG across qualified hitters)
```

OPS+ as canonically defined includes a park-adjustment factor
that requires per-park hitting and pitching factors. Diamond IQ
does not ingest park factors (would require a separate data
source — Fangraphs or Baseball Reference — and per-park
ingestion). We compute a league-relative OPS+ which captures
league-adjustment but omits park-adjustment. The result is a
player's OPS+ relative to the league mean, but not adjusted for
whether they play in Coors Field vs Petco Park. Documented
acknowledged limitation; future polish item if park factors are
added.

### 4. FIP — cFIP backsolved from our own qualified pitchers

```python
FIP = (13·HR + 3·(BB + HBP) - 2·K) / IP + cFIP
cFIP = lgERA - (Σ(13·HR + 3·(BB + HBP) - 2·K) / Σ IP)   # league
lgERA = 9 · Σ ER / Σ IP                                  # league
```

Computing cFIP from our own qualified-pitcher aggregates means
the league-aggregate FIP matches the league-aggregate ERA by
construction. This is the right shape for a portfolio analytics
product: every number we display can be re-derived from the
DynamoDB records also in the table, no Fangraphs round-trip.

### 5. Sequencing and idempotency

EventBridge cron at `09:30 UTC` daily — 30 minutes after Phase
5C's 09:00 UTC run, generous buffer for the typical 10-second 5C
runtime plus any boxscore-publication delays. The compute is
**idempotent**: re-invoking with the same upstream data produces
identical outputs (no incrementing counters, no append-only
fields).

### 6. UpdateItem semantics

Three new attributes are written: `woba` and `ops_plus` on
hitter rows, `fip` on pitcher rows. UpdateItem (not PutItem) so
upstream fields like `avg`, `obp`, `era`, `full_name` are never
touched. A computed value of None (zero PA, zero IP, missing
inputs) **omits the attribute entirely** rather than writing a
null placeholder — a hitter either has a numeric `woba` or no
`woba` attribute at all.

### Failure modes and alarms

- **Empty qualified pool** (5C didn't run, or Lambda invoked
  before any data exists) — `ok=False`, `reason="no_qualified_records"`,
  no writes, error log line. `Errors > 0` alarm fires on the
  next exception path; the missing-data path returns cleanly so
  doesn't trip the Errors alarm — the `invocations-zero` alarm
  is the canary for the missed cron, the summary log is the
  canary for the missed data.
- **Degenerate league aggregates** (lgOBP=0 or lgSLG=0) —
  `ok=False`, `reason="empty_league_aggregates"`. Sentinel for
  data corruption upstream.
- **Per-player formula failure** (unparseable string, missing
  field) — log INFO, skip writing the affected stat, increment
  `hitters_skipped` / `pitchers_skipped`. Other stats on that
  player still write.

Five custom metrics under `DiamondIQ/AdvancedStats`:
`HittersComputed`, `PitchersComputed`, `LeagueOBP`, `LeagueSLG`,
`LeagueERA`. The league averages are emitted as metrics so
season-long trends in the league baseline are visible in the
CloudWatch console without re-running the Lambda.

## Amendment — Phase 5E implementation decisions

Phase 5E ships the player API Lambda — six HTTP endpoints fronting
the data ingested in 5B-5D. Single Lambda, route-based dispatch on
`event["routeKey"]`. All six routes share one
`AWS_PROXY` integration on the existing API Gateway HTTP API.

### 1. CloudFront edge caching deferred

The existing CloudFront distribution attaches the AWS-managed
`Managed-CachingDisabled` policy to its only cache behavior — the
distribution exists for WAF coverage, not edge caching. Phase 5E
explicitly does **not** add `ordered_cache_behavior` blocks for
the new endpoints. Per-endpoint `Cache-Control` headers
(`max-age=300` for player; `max-age=600` for leaders;
`max-age=3600` for roster and hardest-hit; `max-age=900` for
standings) are honored by browsers and intermediate proxies but
not by CloudFront.

This is intentional. Adding edge caching is a separate focused
phase: it requires per-path `ordered_cache_behavior`, a
non-disabled cache policy, and a cache-tag invalidation strategy
for ingest-driven updates. Browser caching alone is meaningful
for portfolio-scale traffic — repeated leaderboard loads within
the user's `max-age` window hit browser cache, not Lambda.

### 2. Single Lambda + route-based dispatch

API Gateway HTTP API v2 already does the route-key matching at
the gateway level — the Lambda receives `event["routeKey"]` as
a static string like `"GET /api/players/{personId}"`. The router
is a `dict[str, Callable]` with six entries, dispatch is one
hash lookup. No regex, no fallthrough.

`GET /api/players/compare` and `GET /api/players/{personId}` are
both registered. API Gateway HTTP API v2 routes
literal-segment-priority at runtime regardless of declaration
order, so `/compare` reaches its dedicated handler. The route
table contains both keys to fail loudly if a future config drift
breaks gateway-level routing.

### 3. 503 stubs for unfinished ingestion paths

`GET /api/standings/{season}` and `GET /api/hardest-hit/{date}`
are wired into the dispatch table but return:

```json
{"error": {"code": "data_not_yet_available",
           "message": "...",
           "details": {"season": 2026}}}
```

with HTTP 503. Standings ingestion and `HITS#<date>` ingestion
are deferred to a future Phase 5L+ (standings) or post-MVP
(hardest-hit). Endpoint shape and routing are stable now so the
frontend can integrate against a fixed contract; the response
becomes a 200 with a real payload when ingestion lands. No URL
or response-shape change required at that point.

### 4. Decimal handling — lossy convert to int or float

DynamoDB returns every numeric attribute as `Decimal`. JSON
doesn't natively serialize Decimal. The `_decimal_default` JSON
encoder hook converts integral Decimals to `int` and fractional
Decimals to `float`. This is lossy in principle (`0.1` is not
exactly representable in float) but the project's stat values
are display-precision (3 decimal places max) — well within
float's representable range. Frontend consumes JSON-native
numbers without `parseFloat` ceremony.

### 5. `_LEADER_STATS` config drives sort field and direction

Single source of truth, two-level dict keyed by group then URL
token:

```python
_LEADER_STATS = {
    "hitting": {"avg": {"field": "avg", "direction": "desc"}, ...},
    "pitching": {"era": {"field": "era", "direction": "asc"},
                 "k":   {"field": "strikeouts", "direction": "desc"}, ...},
}
```

URL tokens may differ from storage attribute names (URL `k` →
stored `strikeouts`). Direction encodes ascending vs descending
per stat — `era`, `whip`, `fip` are lower-is-better.
Adding a new leaderboard stat is one config entry; no handler
code changes.

### 6. Four CloudWatch alarms

- `errors > 0` (5-min) — unhandled exception in any handler.
- `duration > 8000ms` (5-min) — 80% of the 10 s timeout.
- `4xx-rate > 5/min sustained 5 min` — frontend bug, scraper,
  or path-typo storm.
- `runaway-invocations` — auto-added via the `cost_runaway_lambdas`
  set in `alerts.tf` (one shared alarm definition for every
  function in the project).

All routed to the `diamond-iq-alerts` SNS topic.

### 7. Custom metrics under `DiamondIQ/PlayerAPI`

Three metrics emitted per request, dimensioned by `RouteKey` so
per-endpoint latency and request counts are visible:
`RequestCount`, `ResponseTimeMs`, `StatusCode`. Same try/except
emission pattern as 5B/5C/5D — a metrics-API outage does not
fail the request.

## Amendment — Phase 5F implementation decisions

Phase 5F rebuilds the home-page **League Leaders** section to consume
real `/api/leaders` data shipped in Phase 5E. Two of the three cards
in that section are now real (Batting + Pitching); the Standings card
keeps its `DemoBadge` until Phase 5L+ standings ingestion lands.

### 1. `LeadersList` data-fetching wrapper, `LeaderCard` primitive preserved

The existing `LeaderCard` component is purely presentational
(headers + grid layout + children). Phase 5F adds a new
`LeadersList` data-fetching wrapper that calls `useLeaders` and
renders `Skeleton` rows during load, an error+retry state on
failure, an empty state when the partition has no qualifying
players, and the formatted ranked rows on success.

Composition pattern, not rewrite. Same separation as
`DailyRecapSection` (data-aware) wrapping `RecapCard` (pure)
elsewhere in the home page.

### 2. `mlbTeams.ts` static lookup — already existed

The frontend already shipped a 30-team static map at
`frontend/src/lib/mlbTeams.ts` (Phase pre-5F). Phase 5F reuses
`getMlbTeam(id: number) → MlbTeam | undefined` for the
integer-team-id → display-metadata bridge. Returning `undefined`
for unknown IDs lets the component render a gray sentinel chip
with `?` rather than crash. A `console.warn` fires on the first
unknown ID per session so dev sees the gap.

Source citation in the file header: official MLB Stats API
team IDs (`https://statsapi.mlb.com/api/v1/teams?sportId=1`).
Stable across seasons; new expansion teams require a one-line
addition.

### 3. `formatStat(stat, value)` helper

Single-source-of-truth for stat-value presentation in
`frontend/src/lib/stats.ts`. Rules:

- Rate stats already-formatted as strings by the API
  (`avg`, `obp`, `slg`, `ops`, `era`, `whip`) pass through
  unchanged.
- `woba` (Decimal from Phase 5D, parsed to number by JSON) →
  3 decimals with leading zero stripped (`.399`).
- `fip` → 2 decimals (`3.67`).
- `ops_plus` → integer (`148`).
- Counting stats (`home_runs`, `strikeouts`, `wins`, `saves`,
  `rbi`, `hr`, `k`) → integer.
- `null`/`undefined` → em-dash.

Adding a new leader stat is a one-line config in this file plus
one entry in the `_LEADER_STATS` config dict on the backend
(see Phase 5E amendment).

### 4. URL stat token vs storage attribute name

`/api/leaders/hitting/hr` returns rows with `home_runs: 25`,
not `hr: 25`. The Phase 5E response payload includes a `field`
attribute that names the actual storage attribute used to look
up the value on each row. `LeadersList` reads
`response.data.field` and uses it to project values from each
row, so the URL-token-vs-storage-name divergence stays
encapsulated in the API. The component prop `primaryStat`
remains the URL token (used to format and as the CSS column
identity).

### 5. Per-card DemoBadge on Standings only

The previous home-page section had one `DemoBadge` at the
SectionBar level covering the whole "League Leaders" group.
Phase 5F removes the section-level badge and adds a per-card
overlay badge only on the standings card. Visual signal: two
of three cards are real, the third is still demo, no
ambiguity.

When standings ingestion lands (Phase 5L+ option), the card
gets rewired to a new `StandingsList` data-fetching wrapper
calling `useStandings`, the per-card DemoBadge is removed, and
the section is fully un-demoed.

### 6. Multi-stat-per-card uses N parallel `useLeaders` calls — future polish

For v1, the Batting card displays HR (primary, sort key) plus
AVG / OPS / wOBA (secondary). The current implementation makes
**one** API call (HR) and reads the secondary stat values from
the same row payload — the API returns the full record per
player. Multi-stat-per-card is therefore a single fetch, not N.

A future polish item, **not required for v1**: a
`/api/leaders/multi?stats=hr,avg,ops,woba` endpoint that takes
N stats and returns the *union* of leaders across all queried
boards (top-N for each stat, deduped). Useful when the secondary
stats include a player who isn't in the primary stat's top-N.
For Phase 5F's v1 scope, the simpler "show what the primary
stat's top-N looks like across these other stats too" is the
right product behavior.

### 7. Bundle size delta

+2.1 KB raw, well under the 2 KB target give-or-take. Adds:
the `LeadersList` component (~3 KB source, tree-shaken to ~1.5 KB
in build), the `useLeaders` hook (~0.3 KB), the `formatStat`
helper (~0.4 KB), and the `LeadersResponse` types (zero runtime
cost). React Query is already in the bundle from previous
phases; no new vendor weight.

## Amendment — Phase 5H implementation decisions

Phase 5H rebuilds the home-page **Player Comparison** section
(`CompareStrip`) to consume real `/api/players/compare` data. The
DemoBadge for this section is removed; the section now renders
real side-by-side comparisons of MLB players from the qualified
pool.

### 1. Picker mechanism — curated featured matchups, not search

v1 ships a small list of 4 hand-picked matchups in
`frontend/src/lib/featuredComparisons.ts` rendered as horizontal
scrollable tabs. Each matchup pairs two real MLB person IDs
verified to be in the current qualified pool.

A search-based picker (typeahead → `/api/players/search?q=`
backend endpoint) is a Phase 5K+ enhancement. Reasoning: the
home-page comparison is editorially curated content, not a
research tool. A search-based player picker is a different UX
(the `/compare` route, where the user opts into comparison
work) — out of scope for the home-page card.

### 2. Featured matchup curation + maintenance

Four matchups shipped at v1, all type-matched
(hitter-vs-hitter or pitcher-vs-pitcher):
- Judge vs Alvarez — top-3 wOBA matchup
- Trout vs Olson — veteran top-10 wOBA
- Sale vs Soriano — pitcher matchup, established vs breakout
- Schlittler vs Wrobleski — two top-5 ERA breakout starters

**Maintenance note:** the player IDs are real and stable, but a
featured player can drop out of the qualified pool mid-season
(injury, demotion, trade). The list should be reviewed
periodically and rotated when a featured player goes cold or
gets traded. The component renders graceful fallbacks (see #3) so
a stale matchup doesn't crash the section — it just shows the
fallback message until the list is updated.

### 3. Edge-case handling — three fallback states

The component handles three distinct degenerate cases, each with
a clear user-facing message:

- **Both players are hitters** OR **both are pitchers** —
  render the side-by-side stat comparison (the common path).
- **One hitter, one pitcher** — `compareStatBetter` would compare
  meaningless stat pairs. Render
  `"Player types incomparable (one hitter, one pitcher)"`. Defensive
  only; featured matchups are all type-matched.
- **One or both players have BOTH hitting and pitching null** —
  uncommon mid-season case for trade-deadline call-ups, IL
  stints, or players outside the qualifying-PA threshold.
  Verified live during planning: Germán Márquez had both null.
  Render `"Insufficient season data for at least one player"`.

The component still renders the player names and team chips above
the message in both fallback paths, so the user sees *who* the
matchup is and understands *why* the comparison is empty.

### 4. Direction-aware highlighting + bar inversion

`compareStatBetter(stat, a, b)` in `lib/stats.ts` returns
`'a' | 'b' | 'tie' | null`, direction-aware via the
`ASCENDING_STATS` set (`era`, `whip`, `fip`). Returns `null` when
either value is missing/unparseable so the UI renders neutral
styling instead of a misleading winner.

Bar fill math is also direction-aware: for ascending stats the
fill is `(max - value) / max` instead of `value / max`. So lower
ERA renders as a longer bar — visually-longer = better remains
the user's mental model regardless of direction.

### 5. Self-scaling per-row max

`max = max(a, b) * 1.05` per stat row, computed at render time.
No hardcoded ceilings (the previous demo had a `COMPARE_MAX`
record with per-stat constants like `AVG: 0.350`). 5% headroom
prevents either bar from pegging at 100% of the track.

### 6. Stat list per group

6 rows each:

- **Hitting:** AVG, HR, RBI, OPS, wOBA, OPS+
- **Pitching:** ERA, K, WHIP, FIP, W, SV

Mix of traditional triple-crown counterparts (HR/RBI for hitters;
W/SV for pitchers) with the 5D-computed advanced stats (wOBA,
OPS+, FIP) so the modern analytics signal lives next to the
familiar one. Adding a row is a one-line config in
`HITTING_ROWS` / `PITCHING_ROWS` plus a stat-format entry in
`formatStat` if the new stat needs custom rendering.

### 7. Bundle size delta

+5.0 KB raw (329 KB → 334 KB), gzip 102.2 → 103.4 KB. Larger
than Phase 5F's +2.1 KB because the Phase 5H scope was meaningfully
broader: a full CompareStrip rewrite with tabs, picker state,
six stat rows, three fallback states, the
direction-aware comparison helper, and the featured-matchup
data. React Query and other vendor weight are already in the
bundle.

## Amendment — Phase 5L implementation decisions

Phase 5L ships two ingest Lambdas: `diamond-iq-ingest-standings`
(daily refresh of all 30 team standings) and
`diamond-iq-ingest-hardest-hit` (daily top-25 batted balls by
exit velocity). The Phase 5E `/api/standings/{season}` and
`/api/hardest-hit/{date}` route handlers are rewired to project
the populated partitions into 200 responses; the 503 fallback
remains for empty partitions (future seasons, dates pre-dating
ingestion).

### 1. Standings ingest — single API call, 30 rows

`/standings?leagueId=103,104&season=YYYY` returns 6 division
records (3 AL + 3 NL) each with 5 teamRecords. The handler
flattens to 30 `STANDINGS#<season>/STANDINGS#<teamId>` rows.
Idempotent: every PutItem overwrites in place. No TTL — the
partition is overwritten daily, never expires.

`gamesBack` is stored as the literal API value (e.g., `"-"` for
division leaders, `"1.5"` for trailing teams). Frontend transforms
to em-dash for display; storing the upstream value keeps the
projection round-trippable.

### 2. Hardest-hit ingest — SK encoding for descending sort

Default DynamoDB Query returns SKs in ascending order. Phase 5L
encodes the HIT SK as `HIT#<inverted_velo>#<gamePk>#<eventIdx>`
where `inverted_velo = 9999 - int(round(launch_speed * 10))`.
A 117.8 mph hit becomes `8821`, sorting before a 100.0 mph hit
at `9000`. The route handler can return top-N with a plain
`Limit=N` query; no `ScanIndexForward=False` flip, no
sort-in-Lambda.

Cap rationale: the hardest-hit ball in MLB history is ~123 mph
(Stanton, 2017). 999.9 mph is impossibly high. If a malformed
launchSpeed exceeds 999.9 (negative inversion), clamp to 9999
(sorts to the bottom — "loud sentinel" so dev investigation is
obvious).

### 3. Bunt filter

`hitData.trajectory in {"bunt_groundball", "bunt_popup"}` is
filtered out before sort. The "hardest-hit-of-the-day"
editorial frame doesn't include 60 mph bunts even when they
happen to be the hardest contact a particular pitcher allowed.
A future "all batted balls of the day" feature would drop this
filter; currently nothing else consumes the HITS partition.

### 4. Playoff odds — deferred, three future paths

The MLB Stats API does NOT expose playoff odds. The
`magicNumber` and `eliminationNumber` fields are deterministic
clinch math (W/L arithmetic), not probabilistic forecasts. We
omit playoff odds from the standings record entirely rather
than show fake precision. Three future-options paths if the
project wants probabilistic odds later:

- **(a) Fangraphs/Baseball-Reference scrape via pybaseball.**
  Real ZiPS/SRS-derived odds; adds an external dependency and
  scrape-fragility surface.
- **(b) Compute magic/elimination numbers locally from the W/L
  data the API DOES expose.** These are deterministic from
  current standings + remaining games; no probability, but
  meaningful to fans. Lowest-effort future addition.
- **(c) Commercial source (e.g., Sportradar, Stats Perform).**
  Highest-quality data; meaningful licensing cost; out of
  scope for a portfolio project.

Recommendation if revisited: option (b) for v1 of any
playoff-odds enhancement, with the magic/elimination math
documented in code as "deterministic clinch math, not
probabilistic forecast."

### 5. Frontend visual space — Phase 5I rebuild

The current demo `TeamGridCard` renders a fake "Playoff %" field
("99.4%", "94.1%"). When Phase 5I rebuilds that card on real
standings data, the playoff-odds field will be dropped. The
visual space it occupied needs a replacement; suggested
candidates:

- vs-Division record (e.g., "12-7 vs East")
- Run differential ("+47" — already stored in the standings row)
- Last-10 sparkline (already stored as "8-2"; rendering as
  10 mini-cells of W/L color is straightforward)

Specific choice deferred to Phase 5I.

### 6. Cron sequencing

Daily crons run in this order:

```
09:00 UTC — ingest-daily-stats          (Phase 5C)
09:15 UTC — ingest-standings            (Phase 5L)
09:30 UTC — compute-advanced-stats      (Phase 5D)
09:45 UTC — ingest-hardest-hit          (Phase 5L)
12:00 UTC — ingest-rosters-daily        (Phase 5B)
```

Standings runs between 5C and 5D because it's independent of
both — it pulls fresh upstream data unrelated to per-player
stats. Hardest-hit runs last because feed/live payloads can
take a few extra minutes to settle after a game's Final state.

### 7. Maintenance note

Phase 5L's two new Lambdas bring the project's daily-cron count
to **5**, all routed through CloudWatch alarms (errors,
duration-near-timeout, invocations-zero) and the cost-runaway
set in `alerts.tf`. A missed cron fires the `invocations-zero`
alarm within 24 hours; a slow run fires duration-near-timeout
within 5 minutes; an unhandled exception fires errors within 5
minutes. No active monitoring required.

## Amendment — Phase 5I implementation decisions

Phase 5I rebuilds the home-page **Team Dashboards** section
(`TeamGridSection` / `TeamCard`) and the **Standings · PL West**
card in the Leaders section (`StandingsCard`) on real
`/api/standings/{season}` data. DemoBadges removed from both;
all three cards in the Leaders section are now real.

### 1. Boundary type-coercion convention (project-wide)

API response types include numeric fields stored upstream as
strings (e.g., `division_rank` and `league_rank` come back as
`"1"`, `"2"`, ... in the standings payload). Frontend type
definitions coerce these at the parse boundary so the rest of
the codebase deals only with sortable numerics. Apply
consistently to any future API integration where MLB upstream
uses string-typed numerics.

Implementation (`frontend/src/types/standings.ts`):

```typescript
export interface StandingsRecordRaw {
  division_rank: number | string;  // upstream may send either
  league_rank:   number | string;
  // ...
}

export interface StandingsRecord extends Omit<StandingsRecordRaw, 'division_rank' | 'league_rank'> {
  division_rank: number;  // coerced; rest of app sees only numbers
  league_rank: number;
}

export function parseStandingsResponse(raw): StandingsResponse {
  // ... coerces ranks via Number.parseInt, falls back to 999 sentinel
}
```

`fetchStandings` in `lib/api.ts` calls `parseStandingsResponse`
on the raw response so consumers downstream (the hook, the
component, the sort) never see strings. Sort, filter, and
arithmetic all just work.

### 2. Composition: `TeamGridSection` wrapper, `TeamCard` primitive

`TeamGridSection` is the new data-fetching wrapper that calls
`useStandings` and renders 6 `<DivisionRow>` blocks (3 AL on
top, 3 NL below). Each row renders 5 `TeamCard` tiles sorted by
`division_rank` ascending.

`TeamCard` is the per-team tile primitive — record, last-10,
streak, run differential. Same MiniStat grid as the previous
demo; only the data source changed.

### 3. Run-differential replaces playoff-odds visual

Phase 5L confirmed playoff odds are not in the response. Phase
5I replaces the demo's "Playoff %" 4th MiniStat with
**run differential** (`+47` / `-12`), color-coded green/red.
The bottom progress bar (which previously scaled by playoff %)
now scales by **win pct** (0..1) so a .643 team shows a
64%-filled bar — same "team strength" visual affordance with
real data.

### 4. Streak + run-diff color semantics

Reuses the existing color tokens consistently:

- `streak_code` starts with `"W"` → `text-good` (green)
- `streak_code` starts with `"L"` → `text-bad` (red)
- `streak_code` is null/empty → `text-paper-4` (neutral)
- `run_differential > 0` → `text-good` with `+` prefix
- `run_differential < 0` → `text-bad` (sign already in value)
- `run_differential === 0` → neutral `text-paper-2`

### 5. Standings · AL West card — single-division v1

The third card on the Leaders section (previously demo
"Standings · PL West") becomes
`<StandingsCard divisionId={200} title="Standings · AL West" />`.
Reuses the same `useStandings` hook as `TeamGridSection`; React
Query shares the cache so the home page makes exactly **one**
API call regardless of how many components consume it.

Single-division v1; multi-division extension via
`divisionIds={[...]}` is a future polish — would let the user
toggle between divisions or render a tabbed picker in the same
visual slot.

### 6. Visual density consideration (future polish)

The 30-team grid is significantly denser than the previous
8-team demo. If density becomes an issue at narrow viewports or
in usability testing, future polish items:

- Collapsible league sections (click "American League" to
  collapse the 3 AL division rows).
- Highlighted division leaders (visual emphasis on the rank-1
  team in each row, e.g., subtle accent border).
- Progressive disclosure: first paint shows only AL/NL summary
  (6 cards, one per division leader), with a "Show all 30"
  affordance.

Not blocking for v1. Current desktop-first layout uses
`grid-cols-2 sm:grid-cols-3 lg:grid-cols-5` per division row,
which collapses cleanly to 2-up on narrow viewports.

### 7. Bundle size

Two new components plus the standings type module and division
lookup; `useStandings` reuses TanStack Query (already in the
bundle). Estimated +3 KB raw — measured at commit time.

## Amendment — Phase 5G implementation decisions

Phase 5G rebuilds the home-page **Stat of the Day · Hardest-hit
balls** card on real `/api/hardest-hit/{date}` data shipped in
Phase 5L. This is the last demo card on the home page; with this
phase, **all four Option-5-scoped sections (LeaderCard,
CompareStrip, TeamGridCard, HardestHitChart) are real** and the
section-level `<DemoBadge />` is removed. Closes Option 5.

### 1. Default to yesterday, not today

The Phase 5L cron runs at 09:45 UTC and ingests **yesterday's**
Final games (a game must reach `detailedState == "Final"` before
its `feed/live` payload is queryable). Today's `HITS#<today>`
partition is therefore empty until tomorrow's run. The card
defaults to `yesterdayUtcDate()` — the freshest data the
ingestion pipeline can produce — and the section subtitle reads
`"Hardest-hit balls · yesterday"` to match.

A future polish item if real-time ingestion lands (per-game
`status: Final` triggered via Streams instead of a daily cron):
flip the default to `today`, render a per-game progressive
update, and re-add a "yesterday" toggle. Out of scope for v1.

### 2. 503 → graceful empty state, NOT error retry

The Phase 5E/5L route returns HTTP 503 with
`error.code = "data_not_yet_available"` when the partition is
empty (cron hasn't fired for that date, or future dates).
TanStack Query surfaces this as `isError === true` with
`error.status === 503`. The component branches on that:

```tsx
if (isError && error?.status !== 503) {
  return <ErrorWithRetry .../>;
}
const hits = data?.data.hits ?? [];
if (hits.length === 0) {
  return <NoDataYet date={date} />;
}
```

503 is treated as a clean empty-state message ("No hardest-hit
data for 2026-04-28 yet."), no retry button. Non-503 errors
still surface the retry affordance. Same UX framing as the
Phase 5E backend's intent: data-not-yet-available is a known,
expected steady state during the ingestion-pipeline cold-start
window — not a failure.

### 3. Bar scaling — pinned-100-mph floor + per-row gradient

Same scaling math as the original demo with one refinement: the
visual `min` is `min(100 mph, lowest-mph-in-set)` so even the
shortest bar in the set has visible length on the track. The
opacity gradient (`0.35 + 0.65 * (1 - i/N)`) and accent color
on rank-1 are preserved from the demo.

### 4. Team chip is gray sentinel — `team_id` not in response

The Phase 5L backend payload doesn't include `team_id` per hit
(only `batter_id`). Looking up the team would require a
secondary `BatchGetItem` against `PLAYER#GLOBAL` to resolve
`batter_id → team_id` — out of scope for Phase 5G. The frontend
renders a neutral `?` chip on each row instead. Future polish:
**extend the backend hit projection to include `team_id`** from
the boxscore line (the data is already available in the
`feed/live` payload during ingest; just not currently captured).
That's a Phase 5L follow-up, not a Phase 5G blocker.

### 5. One-time test-data prep

The Phase 5L cron's first natural firing populates
`HITS#<yesterday>` automatically, but the cron may not have
fired between Phase 5L deploy and Phase 5G frontend dev. A
one-time manual invocation seeded the partition for development:

```bash
aws lambda invoke --function-name diamond-iq-ingest-hardest-hit \
  --region us-east-1 /tmp/hh.json
```

This is **not** a recurring ops procedure — the cron handles
populating the partition on its daily schedule. The manual
invocation is documented here for the historical record only.
After Phase 5G's first dev session, the partition is populated
and remains so as long as the cron continues firing.

### 6. Closes Option 5

With Phase 5G shipped:

- **Zero `<DemoBadge />` instances on `HomePage.tsx`.** Every
  data-driven card on the home page is backed by a real
  ingestion + API endpoint pair.
- **All four ADR-012-scoped sections are real:**
  - `[6]` Leaders → LeadersList + StandingsCard (Phases 5F + 5I)
  - `[7]` Stat of the Day → HardestHitChart (Phase 5G)
  - `[8]` Player Comparison → CompareStrip (Phase 5H)
  - `[9]` Team Dashboards → TeamGridSection (Phase 5I)
- `LiveGamePage` has 3 demo badges that are **out of scope for
  Option 5** (live-game subviews, separate workstream).

Footer copy bumped to `v4.14`. No further Option-5 work
planned; deferred backlog items (CloudFront edge caching,
search-based player picker, multi-division StandingsCard,
playoff odds, multi-stat leaders endpoint, and `team_id` on
hardest-hit rows) remain documented in the relevant phase
amendments.

## Amendment — Phase 5K implementation decisions

Phase 5K adds player headshots to the home page UI. The Phase 5J
CSP allowlist already included `https://img.mlbstatic.com` in
`img-src` proactively — no infrastructure change. Pure frontend
work; no backend or schema changes.

### 1. Direct from MLB CDN, no caching layer

The headshot URL pattern reverse-engineered from MLB.com:

```
https://img.mlbstatic.com/mlb-photos/image/upload/
  d_people:generic:headshot:67:current.png/w_180,q_auto:best/
  v1/people/{playerId}/headshot/67/current
```

The `d_people:generic:headshot:67:current.png` segment is MLB's
default-on-missing transformation — every player ID returns
*something* (real photo or generic silhouette), never a 404.
Confirmed live on `playerId=99999999` (returns the silhouette
PNG with HTTP 200).

Three options were considered for hosting:

| Option | Why it lost |
|---|---|
| **Direct MLB CDN** (chosen) | Free, MLB handles edge optimization, zero infra. |
| Proxy through our S3 + CloudFront | ~$2/mo at portfolio traffic; gives us cache control we don't need; opens a moderation-and-takedown question (do we mirror photos of players who request opt-out?). Deferred. |
| Lambda-fetched + DynamoDB-cached binary blobs | Heaviest option; would only matter at scale we don't have. Rejected. |

Documented in the component's JSDoc so future maintainers can
revisit if MLB changes the URL or imposes hotlink restrictions.

### 2. Component contract

`<PlayerHeadshot playerId playerName size?='sm'|'md'|'lg' />`
at `frontend/src/components/PlayerHeadshot.tsx`. Sizes:

- `sm` 32 px — used in `LeadersList` rows and `HardestHitChart` rows
- `md` 48 px — used in `CompareStrip` per-player slots
- `lg` 96 px — reserved for future player-detail views

Behavior:

- Image first, with `loading="lazy"` so off-screen rows in the
  leader / hardest-hit lists don't block initial paint.
- `decoding="async"` so the main thread doesn't stall when a row
  scrolls into view.
- `onError` fallback to a circular `<span role="img">` showing
  the player's initials on a neutral background. Belt-and-
  suspenders since MLB's URL guarantees a 200, but covers
  network failures, ad-blockers, and the unhappy CDN-down case.
- When `playerId` is missing/null/empty, the initials fallback
  renders directly without attempting the fetch.
- `initialsOf("Aaron Judge") → "AJ"`,
  `initialsOf("Pedro") → "P"`,
  `initialsOf("Fernando Tatis Jr.") → "FT"` (suffix tokens are
  filtered before computing the last initial).

### 3. Integration scope

| Component | Integration | Visual change |
|---|---|---|
| `LeadersList` row | Replaced the team chip with `<PlayerHeadshot size="sm" />` | Rows now lead with the player photo instead of team color. Brand color is still implicit via the photo's team uniform; the swap is a net editorial win — the player IS the row's identity, the team is secondary. |
| `HardestHitChart` row | Replaced the gray sentinel `?` chip (which was a placeholder per Phase 5G amendment §4) with `<PlayerHeadshot size="sm" />` keyed by `batter_id` | Cleanly closes out the Phase 5G "future polish" item — rows now have real player faces instead of placeholder sentinels. Backend `team_id` projection still deferred but no longer load-bearing since the headshot replaces the chip entirely. |
| `CompareStrip` per-player slot | Replaced `<PlayerSilhouette size={46} />` with `<PlayerHeadshot size="md" />` | The placeholder silhouette becomes a real photo. Subtitle (city + position) and full-name typography unchanged. |
| `TeamGridCard` | **No integration.** | The card surfaces team-level data only (record, last-10, streak, run differential); no individual players. Per-spec ("if it surfaces individual players, add small headshots; if purely team-level, skip"). Documented for posterity. |

### 4. No CSP / no infrastructure changes

`Content-Security-Policy: img-src 'self' data: https://img.mlbstatic.com`
was set in Phase 5J specifically to enable this work. No
new directives, no Terraform changes. Verified via DevTools
during the live deploy: zero CSP violations on the home page,
all four headshot integration sites loading photos cleanly.

### 5. Performance impact

Lighthouse pre/post Phase 5K (against the live URL):

| | Before (Phase 5J close) | After (Phase 5K) | Δ |
|---|---|---|---|
| Desktop best-of-2 | 87 | 87 | 0 |
| Mobile | 87 | **90** | **+3** |
| Desktop CLS | 0.011 | 0.012 | +0.001 (noise) |
| Mobile CLS | 0.002 | 0.002 | 0 |
| Bundle (raw) | 339 KB | 340 KB | +0.55 KB |
| CSS bundle | 25.4 KB | 25.8 KB | +0.4 KB |

Mobile gained 3 points, mostly from the explicit `width`/`height`
attributes on every `<img>` (no layout reflow when the image
loads — CLS stays clean) plus `loading="lazy"` deferring
off-screen image fetches. Desktop unchanged. No regression on
either axis.

### 6. Tests

Adds 12 new frontend tests under `PlayerHeadshot.test.tsx`:
initials computation across name shapes, image rendering with
correct CDN URL, lazy/async attributes, alt text, fallback paths
for null/undefined/empty `playerId` and on-error.

Each integrating component (`LeadersList`, `HardestHitChart`,
`CompareStrip`) gains one positive assertion that the integrated
headshot renders an image with the expected MLB CDN URL.

**Total frontend tests: 179 (was 167, +12). All pass.**

### 7. Future polish

- **S3 + CloudFront cache layer in front of MLB's CDN.** Would
  give us cache control, hotlink resilience, and a takedown
  surface if MLB ever objected. Estimated +$2-3/mo at portfolio
  traffic. Not built; deferred until a real need surfaces.
- **Larger `lg` size for player-detail pages.** The component
  supports it (96 px); no consumer renders it yet because the
  player-detail route doesn't exist. Lands when that page does.
- **Hover preview** with extended player metadata. Out of scope.
- **Backend `team_id` projection on hardest-hit rows.** Now even
  lower priority since headshots replace the team chip on that
  card. Probably won't ship.

---

## Phase 5L Amendment — Team-Aggregate Stats + Compare Pages (Apr 2026)

Final Option-5 increment. Closes the feature surface to "feature-
complete": users can now compare any two players AND any two teams
on dedicated full-page routes, with visual delta indicators on
every stat row.

### 1. New ingest path

`diamond-iq-ingest-team-stats` Lambda (256 MB / 60 s) hits MLB's
`/teams/{id}/stats?stats=season&group=hitting,pitching` endpoint
once per team per day at 09:20 UTC. 30 sequential calls, ~6 s
end-to-end, idempotent PutItems into a single
`TEAMSTATS#<season>` partition keyed by `TEAMSTATS#<teamId>`.

**Why a dedicated Lambda instead of extending `ingest_daily_stats`:**
the daily-stats path filters to a qualified-pool (PA ≥ N or
IP ≥ N) by design, which would have silently dropped low-PA teams
or expansion-rebuild rotations. A separate path for the team
aggregate makes the filtering boundary explicit and keeps the
qualified-pool filter unchanged for player leaders.

**Schema:** 22 hitting fields + 30 pitching fields per team, mostly
pass-through from MLB's response. `stolen_bases` was added to the
existing `_season_item` projection in the same phase so player and
team comparison views align on the same SB scale.

### 2. New API routes

Two routes share the existing `diamond-iq-api-players` Lambda
(single-Lambda routeKey dispatch — see ADR 012 Phase 5E section):

  - `GET /api/teams/{teamId}/stats` — single team's aggregate.
    Returns 503 `data_not_yet_available` if the partition is empty
    (cron hasn't fired yet); 400 on non-numeric teamId.
  - `GET /api/teams/compare?ids=...` — 2-4 csv team ids, mirrors
    the `/api/players/compare` contract. 400 on out-of-range count;
    404 if any id has no row.

Both honor `Cache-Control: max-age=900` (15 min) — team aggregates
update daily, so a 15-minute browser cache adds zero staleness in
practice.

### 3. New frontend pages

  - `/compare-players` — full-page version of `CompareStrip`.
    PlayerHeadshot at `size="lg"` (96 px), responsive
    one-column-on-mobile / two-column-on-sm+ header. Featured-
    matchup quick-pick chips reuse `FEATURED_COMPARISONS`; URL
    `?ids=<a>,<b>` makes any pair shareable. Same hitter-vs-
    pitcher and insufficient-data fallbacks as CompareStrip.
  - `/compare-teams` — two `<select>` dropdowns of all 30 teams
    (sourced from the static `mlbTeams` table, no extra round-
    trip), 64 px team logos, separate Team Batting and Team
    Pitching cards. URL `?ids=<a>,<b>` for shareable selections.

Both pages register as lazy chunks (~7 KB gzip 2.5 KB each) so
they don't add weight to the LCP-critical home-page bundle. The
old `/compare` route now redirects to `/compare-players`.

### 4. Visual delta semantics

Both pages reuse the per-row max-with-5%-headroom bar pattern from
CompareStrip. Ascending stats (ERA / WHIP / FIP on the player
page; ERA / WHIP / OPP_AVG on the team page) flip the bar so
visually-longer = better stays the user's mental model. The
team-page `OPP_AVG` token isn't in the player-side
`ASCENDING_STATS` set; rather than expand that set with a stat
that doesn't exist on the player tier, the team page maintains a
small local override set (`TEAM_ASCENDING_LOCAL`).

### 5. Tests

Backend (296 → 305, +9): one ingest test fixture/assertion gained
the `stolenBases` field; 9 new tests covering team-stats ingest
(happy path, per-team failure isolation, teams-fetch failure abort,
idempotent rerun, partial-groups handling, metric emission); 7 new
api_players route tests (happy path, 503 when empty, 400 on
invalid teamId, compare 200 / 404 / 400 for too-few / 400 for
too-many).

Frontend (179 → 200, +21): 4 `useTeamStats` + 5 `useTeamCompare`
hook tests; 6 `PlayerComparePage` + 6 `TeamComparePage` page
tests covering picker mechanics, URL state, success / error
states. **All 200 pass.**

### 6. Cost delta

  - Compute: +30 invocations/day × ~6 s × 256 MB ≈ negligible
    (well below free tier).
  - Storage: 30 rows × ~4 KB ≈ 120 KB/season. One-and-done annual
    growth.
  - Network: 30 MLB requests/day, sequential with 100 ms inter-
    call sleep. Same friendly-burst pattern as the daily-stats
    ingest.

### 7. Observability

3 new alarms wired identically to the existing daily-stats path:
`-errors`, `-duration-near-timeout` (48 s = 80 % of the 60 s
timeout), `-invocations-zero` (24 h period). The existing
`cost_runaway_lambdas` for_each set picks up the new function
automatically — no per-Lambda alarm copy-paste.

### 8. Status

**Feature-complete.** No further roadmap items planned. Future
work, if any, would be quality-of-life: a real `/api/players/
search?q=…` endpoint to replace the URL-driven custom-IDs picker
fallback on the Compare Players page; a per-route Lighthouse CI
gate; a redesigned home-page hero. None of these block shipping.
