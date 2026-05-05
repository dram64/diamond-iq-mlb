# Architecture

Diamond IQ is two cloud-native pieces glued together by an HTTP API:
an ingestion path that pulls MLB Stats API data into DynamoDB on a
1-minute schedule, and a serve path that reads from DynamoDB and
returns JSON to the frontend. Everything runs on serverless AWS.

## Component diagram

```
              ┌──────────────────────────────────────┐
              │            INGESTION                 │
              └──────────────────────────────────────┘

         ┌────────────────────┐
         │ EventBridge rule   │  schedule_expression = "rate(1 minute)"
         │ ingest-schedule    │
         └─────────┬──────────┘
                   │ invoke
                   v
         ┌────────────────────┐         GET /api/v1/schedule
         │ Lambda             │  ────>  https://statsapi.mlb.com/...
         │ ingest-live-games  │  <────  schedule payload (yesterday + today UTC)
         │ python3.12         │
         └─────────┬──────────┘
                   │ put_item (live games only)
                   v
         ┌────────────────────────────────────────────┐
         │ DynamoDB                                   │
         │ table: diamond-iq-games                    │
         │ PK = "GAME#<yyyy-mm-dd>"                   │
         │ SK = "GAME#<gamePk>"                       │
         │ TTL = ttl attribute, ~7 days from write    │
         │ PITR enabled, AES-256 SSE                  │
         └─────────┬──────────────────────────────────┘
                   ^ get_item / query
                   │
              ┌──────────────────────────────────────┐
              │            SERVE                     │
              └──────────────────────────────────────┘
                   │
         ┌─────────┴──────────┐
         │ Lambda             │
         │ api-scoreboard     │
         │ python3.12         │
         └─────────┬──────────┘
                   │ AWS_PROXY (payload v2)
                   v
         ┌────────────────────┐
         │ API Gateway        │  GET /scoreboard/today
         │ HTTP API           │  GET /games/{gameId}
         │ CORS: localhost..  │  $default stage, auto_deploy
         └─────────┬──────────┘
                   │ HTTPS
                   v
              ┌────────────┐
              │  Browser   │
              │  / curl    │
              └────────────┘

  All Lambdas write structured JSON to CloudWatch Logs
  (14-day retention). API Gateway also writes JSON access logs.
```

## Components

### EventBridge schedule
A `rate(1 minute)` rule fires the ingest Lambda 24/7. The Lambda
self-throttles (no DynamoDB writes when no games are live), so the
fixed cadence is fine even during off-season hours. Cost at this rate:
~43,200 invocations/month, well within the 1M Lambda free-tier.

### Ingest Lambda (`functions/ingest_live_games/`)
- Triggered: EventBridge
- Memory: 512 MB, Timeout: 60 s
- Behavior:
  1. Compute `today_utc` and `yesterday_utc`
  2. Fetch the MLB schedule for both dates
  3. Filter to `abstractGameState == "Live"` games
  4. Deduplicate by `gamePk`
  5. Normalize each game to our internal `Game` model
  6. `put_item` each into DynamoDB
- Resilience:
  - One failed MLB API call doesn't block the other date
  - Per-game write failures are isolated; the batch continues
  - Top-level errors return a structured failure summary instead of
    raising (no Lambda automatic retries hammering MLB during outages)
- Observability: every invocation emits a single JSON summary log
  (`live_games_processed`, `games_written`, `games_failed`, both dates)

### API Lambda (`functions/api_scoreboard/`)
- Triggered: API Gateway HTTP API
- Memory: 256 MB, Timeout: 10 s
- Routes:
  - `GET /scoreboard/today` — array of games for a date (defaults to UTC today; `?date=` overrides)
  - `GET /games/{gameId}` — one game (requires `?date=`)
- IAM scoped read-only: `dynamodb:GetItem`, `dynamodb:Query` only
- Defensive boundaries:
  - Date format validation (regex + `datetime.strptime`)
  - 400 / 404 on bad input with structured error codes
  - Top-level `try/except` wrapping every route — internal exceptions
    are logged with full traceback to CloudWatch but the response body
    only contains `{"error": {"code": "internal_error", "message": "internal server error"}}`
- CORS headers on every response (success + error paths alike)

### DynamoDB (`diamond-iq-games`)
- Single-table, PAY_PER_REQUEST
- Partition key (`PK`): `"GAME#<yyyy-mm-dd>"` — the game's UTC date
- Sort key (`SK`): `"GAME#<gamePk>"` — MLB's stable game identifier
- TTL on `ttl` attribute, written 7 days out from each ingest
- Point-in-time recovery enabled (35-day window)
- AWS-owned KMS key (free) for encryption at rest

The single-table layout supports the two access patterns directly:
`list_todays_games(date)` is a `Query` on `PK`, `get_game(pk, date)` is
a `GetItem`. Adding leaderboards or team views later means adding new
PK prefixes to the same table — no schema migration. See [ADR 001](adr/001-single-table-dynamodb.md).

### API Gateway HTTP API
HTTP API (v2) over REST API: cheaper, simpler, and the auto-deploy
$default stage is enough at this scale. CORS is configured at the API
level; no per-route CORS work in the Lambda. Access logs are written
in JSON to a dedicated CloudWatch log group.

### CloudWatch
- Structured JSON logs from each Lambda (timestamp, level, request_id,
  plus arbitrary `extra` fields via the shared `get_logger`)
- 14-day retention on every log group (project standard)
- API Gateway access logs in the same JSON shape

### Terraform
- Bootstrap stack (`infrastructure/bootstrap/`): S3 state bucket,
  DynamoDB lock table. Applied once with local state, then committed
  state lives only locally. Recoverable via `terraform import`.
- Main stack (`infrastructure/`): everything else. Backend is
  S3 + DynamoDB lock. Five modules: `dynamodb`, `lambda`,
  `api-gateway`, `events`, `oidc`.
- Lambda module builds the deploy zip natively from source files via
  `archive_file` `dynamic "source"` blocks — no provisioner, no staging
  directory. Plan-time evaluation only. See [ADR 006](adr/006-archive-file-dynamic-source.md).

### GitHub Actions OIDC
A federated trust between GitHub Actions and AWS IAM lets workflow
runs assume an IAM role without storing AWS access keys in GitHub
Secrets. The trust policy scopes to `repo:dram64/diamond-iq:*`. The
deploy role's permissions are scoped by ARN pattern to project
resources only (`role/diamond-iq-*`, `function:diamond-iq-*`, etc.).
See [ADR 005](adr/005-oidc-vs-iam-user-credentials.md).

## Design decisions

### Serverless over containers / VMs
At our scale (a few hundred reads per minute, ~43k Lambda invocations
per month), Lambda + DynamoDB pricing is effectively free. Containers
mean an always-on cluster, ALB hours, and per-host patching. We don't
need any of that.

### DynamoDB over RDS
The data model is simple lookups by composite key. We don't need
relational queries, and we want the schemaless flexibility to add new
entity types (teams, players) without migrations. PAY_PER_REQUEST
billing means zero idle cost.

### HTTP API over REST API
HTTP API costs ~70% less per million requests, has lower latency, and
its simpler integration model (AWS_PROXY + payload v2) is everything
this project needs. REST API's extra features (request validation,
API keys, usage plans, x-ray) are overkill here.

### Two-date ingestion window
MLB groups games by *local* date but their `gameDate` field is in UTC.
A 7pm-Pacific start lives under local date X but the UTC date can be
X+1 once the inning crosses midnight UTC. Querying both today and
yesterday UTC on every ingest covers the entire spectrum of in-flight
games regardless of wall-clock time. See [ADR 004](adr/004-two-date-ingestion-window.md).

### OIDC over long-lived credentials
A leaked GitHub Secret with `aws_access_key_id` is the most common AWS
breach pattern in CI/CD. OIDC means no static credentials exist to
leak: GitHub mints a short-lived token per workflow run, AWS verifies
it via the OIDC trust, and the resulting STS session expires in an
hour. See [ADR 005](adr/005-oidc-vs-iam-user-credentials.md).

## Cost (monthly, at current scale)

All pricing is `us-east-1` and assumes free-tier eligibility.

| Service | Usage | Cost |
| --- | --- | --- |
| Lambda | ~43k ingest + ~1k API invocations, < 1 GB-second × < 50,000 | $0 (free tier covers 1M req + 400k GB-sec) |
| DynamoDB | < 100k reads, < 50k writes, < 1 GB storage | $0 (free tier covers 25 RCU + 25 WCU equivalent + 25 GB) |
| API Gateway HTTP API | < 10k requests | < $0.01 (no free tier; $1.00 / 1M requests) |
| EventBridge | 43,200 invocations | $0 (free tier covers all custom events) |
| CloudWatch Logs | < 5 GB ingested + stored | $0–1 (5 GB free, then $0.50/GB) |
| S3 (state bucket) | < 1 MB | $0 (free tier covers 5 GB) |
| Data transfer out | minimal (frontend dev) | $0 (1 GB free) |

Realistic monthly bill: **under $1** until traffic grows substantially.

The billing alarm threshold (set in CloudWatch) is configured at $10
to catch any runaway behavior with a 10x margin.
