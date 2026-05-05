# ADR 010 — WAF, CloudFront fronting, rate limiting, and the COUNT-first rollout

## Status
Accepted

## Context
Diamond IQ Phase 9 shipped a public HTTP API at
`https://7x9tjaks0d.execute-api.us-east-1.amazonaws.com` serving
real MLB data and AI-generated content. With the API publicly
reachable, the project needed a security engineering layer to
demonstrate operational defenses on a live deployed service.

Five things had to be settled:

1. Where the WAF actually attaches (API Gateway HTTP API isn't a
   supported WAF target).
2. Which rules to ship and at what action level.
3. How to roll out without locking ourselves out.
4. How to express geo blocking and dev-IP carve-outs without
   committing IPs to source.
5. How to alarm on attack volume without paging on background noise.

## Decision

### 1. CloudFront fronts the HTTP API; WAF attaches to CloudFront

**AWS WAFv2 cannot attach to API Gateway HTTP APIs (v2).** Supported
targets are CloudFront, API Gateway REST APIs (v1), Application Load
Balancers, AppSync, Cognito User Pools, App Runner, and Verified
Access. A bare `aws wafv2 associate-web-acl` against an HTTP API
ARN is rejected.

The standard production pattern for this gap is **CloudFront in
front of the HTTP API**. CloudFront accepts a generic HTTPS origin,
WAF attaches to the CloudFront distribution, and traffic reaches
the HTTP API only after passing the WAF check at the CloudFront
edge. The HTTP API itself stays unchanged.

```
          ┌────────────┐    ┌──────────┐    ┌─────────────────┐
viewer ──▶│ CloudFront │───▶│  WAFv2   │───▶│ API Gateway HTTP│
          │ (edge)     │    │ Web ACL  │    │ → Lambda        │
          └────────────┘    └──────────┘    └─────────────────┘
```

CloudFront uses the AWS-managed cache policy `CachingDisabled` (no
caching of API responses) and the AWS-managed origin request
policy `AllViewerExceptHostHeader` (forwards every viewer header
to the origin except Host — necessary because API Gateway
requires its own Host header to route correctly).

The HTTP API URL is preserved as a **documented ops-only debugging
bypass**. The frontend points at the CloudFront URL. Every browser
request reaches the API only after passing every WAF rule.

### 2. Managed rule groups + custom rules + rate limiting

Eight rules in priority order. Lower priority = evaluated first.

| Pri | Rule | Type | Default action |
|----:|---|---|---|
| 0   | `dev-allow-list` (only if CIDRs supplied) | Custom IP set | Allow |
| 10  | `aws-managed-ip-reputation` | AWS managed | Count |
| 20  | `aws-managed-common` | AWS managed | Count |
| 30  | `aws-managed-known-bad-inputs` | AWS managed | Count |
| 40  | `aws-managed-bot-control` (COMMON tier) | AWS managed | Count |
| 50  | `block-known-bad-user-agents` | Custom regex | Block |
| 60  | `geo-block` | Custom geo | Count when `enable_geo_blocking=false` |
| 70  | `rate-limit-sensitive-paths` | Custom rate-based | Block 429 |
| 80  | `rate-limit-default` | Custom rate-based | Block 429 |

The Web ACL **default action is Allow**. Every block is explicit
and logged with the rule that matched. Default-deny would lock out
legitimate traffic during the COUNT-mode observation period.

### 3. COUNT-first rollout for managed groups, BLOCK-day-one for custom rules

AWS-managed rule groups ship in **Count mode** for the observation
week. A new rule group can occasionally false-positive on a real
client request — usually a content-type mismatch or a body shape
that triggers a SQL-injection signature. Count mode publishes the
rule's "would have blocked" decision to CloudWatch without actually
blocking, so we can observe a week of real traffic, look at which
rules would have fired and against what, and decide whether to
flip to Block per group.

`var.managed_rule_actions` is a `map(string)` keyed by short
rule-group name (`common_rule_set`, `known_bad_inputs`,
`ip_reputation_list`, `bot_control`) so each group flips
independently. Once observation is done, `terraform apply` with a
single key flipped from `count` to `block` enforces that group.

Custom rules ship in **Block mode** from day one because we
authored their conditions and we know they don't false-positive
against legitimate clients. The bad-User-Agent rule matches the
literal substring `sqlmap` (and friends) in the UA header — no
real client sends those. Rate-limit rules apply to high-volume
abuse; legitimate use stays well under the threshold.

### 4. Geo opt-in by default; dev allow-list lives outside source

`enable_geo_blocking` defaults to `false`. The geo rule still
runs — in **Count mode** — so we get visibility on traffic from
the blocked country list (`CN`, `RU`, `KP`, `IR`) without
actually rejecting anyone. Flip the variable to `true` to enforce.

Reasoning: geo blocking is genuinely lossy. A real user behind a
VPN exit in a blocked country gets a 403 with no useful error
message. For a portfolio API the blast radius of accidental
exclusion outweighs the marginal benefit during normal operation.
We keep visibility (Count mode) so we can decide, with data,
whether the blocked-country traffic is actually abusive.

`dev_allow_list_cidrs` exists for the same reason: a developer
testing rate-limit behavior or running a burst of integration
tests from their workstation should not have to wait for WAF
counters to reset every time. The variable is supplied via
`terraform.tfvars` (gitignored) or `TF_VAR_dev_allow_list_cidrs`,
**never committed**. When empty (production default) the
allow-list rule is omitted from the Web ACL entirely; no rule = no
risk of a stray allow.

### 5. Rate-limit thresholds: 2000 default, 300 sensitive

Rate-based rules in WAF aggregate over a fixed 5-minute window
and key by source IP. Two limits:

- **`rate-limit-default`** (priority 80) — 2000 req/5min/IP for
  every path **except** the welcome route `/`. The welcome route
  stays unrate-limited so portfolio click-throughs (a hiring
  manager pasting the URL into a browser bar) don't surface a
  hostile error during normal evaluation. 2000/5min works out to
  ~6.6 req/sec sustained — well above any honest interactive
  user, well below distributed scrape volume.

- **`rate-limit-sensitive-paths`** (priority 70) — 300 req/5min/IP
  scoped down to `/content/today` and `/scoreboard/today`. These
  are the data-fetching endpoints a scraper would hammer if they
  wanted to mirror the MLB feed. 300/5min works out to 1 req/sec
  sustained — comfortable for normal use; scraper-hostile.

Both rules use a `block { custom_response { response_code = 429 } }`
action so a tripped client gets a meaningful HTTP status, not a
generic 403.

### 6. Logging to CloudWatch Logs, not Kinesis Firehose

WAF supports two log destinations: Kinesis Firehose (industry
standard) and CloudWatch Logs (newer, simpler). For a portfolio
project with low traffic volume, CloudWatch Logs costs
fractions of a cent per month and gives us CloudWatch Insights
queries directly against the data. Firehose adds a moving part
(delivery stream + S3 bucket + lifecycle policy) for no benefit
at our scale.

WAF requires the log group name to start with `aws-waf-logs-`.
The Terraform module enforces this in code:
`name = "aws-waf-logs-${var.name_prefix}"`. Retention is 14 days
(matches the rest of the project's log groups).

### 7. Alarms with realistic thresholds

Two alarms wire to the existing `diamond-iq-alerts` SNS topic:

- **`diamond-iq-waf-blocked-requests-spike`** — sum of
  `BlockedRequests` (across all rules) > 1000 in any 1-hour
  window. Background internet scrape happily fills the "any block
  at all" bucket; the threshold is set high deliberately so the
  alarm only fires on traffic that genuinely warrants attention.
- **`diamond-iq-waf-allowed-requests-drop`** — anomaly-detection
  alarm using `ANOMALY_DETECTION_BAND(m1, 4)` against
  `AllowedRequests`. Detects sudden drops below the learned
  baseline, which is the signal for "we just over-blocked
  ourselves with a rule change." Anomaly detection needs ~2 weeks
  of data to baseline; until then the alarm sits at
  INSUFFICIENT_DATA, which doesn't breach.

The original spec called for a fixed "75% drop" threshold; rejected
in favor of the anomaly band because portfolio traffic is too low
and irregular for a fixed absolute floor to mean anything. Anomaly
detection self-tunes.

## Consequences

### Positive
- **Real WAF coverage on user traffic.** Every browser request
  now passes through 8 evaluation rules at the CloudFront edge
  before reaching API Gateway. Bad-User-Agent traffic and
  high-volume scrape traffic are blocked at the edge.
- **Observability without enforcement risk.** Managed rule
  groups in Count mode give us a week of "what would happen if
  this were enabled" data, with full request samples logged to
  CloudWatch, before we commit to blocking.
- **Independent flip per managed group.** No big-bang
  transition; each group flips on its own schedule once we've
  read its sample data.
- **Geo and dev allow-list are opt-in by config, not by code.**
  No PR required to add a dev IP or to enable geo blocking;
  Terraform variables flip via `terraform.tfvars`/`TF_VAR_*`.
- **Sensitive endpoints are rate-limited at a lower threshold**
  than the rest of the API. Scrapers hit the 300/5min ceiling
  before the 2000/5min one.
- **End-to-end alerting from existing infrastructure.** WAF
  metric alarms reuse the `diamond-iq-alerts` SNS topic, the
  confirmed email subscription, and the CloudWatch
  metric/alarm/SNS pipeline already proven by the Lambda
  alarms.

### Negative
- **CloudFront adds a network hop and ~10-15 minutes of edge
  propagation per Terraform change.** The Terraform apply itself
  returns quickly (`wait_for_deployment = false`) but global
  edges may serve stale config briefly after a change.
- **Custom domain not configured.** The CloudFront URL is the
  default `*.cloudfront.net` form; future polish would attach a
  branded domain via ACM. Acceptable for portfolio.
- **CORS depends on origin behavior.** API Gateway sets the CORS
  headers; CloudFront forwards them via the origin request
  policy. If we ever caching-enable a route, we have to be
  careful that `Access-Control-Allow-Origin` doesn't get cached
  against a single origin. For now, `CachingDisabled` removes
  the risk.
- **WAFv2 description-field regex is restrictive.** Resource
  descriptions reject semicolons, parentheses, em-dashes, and
  most punctuation. Painful but enforced at apply time, not at
  plan time, so Terraform users can hit it after a long apply.
- **CloudWatch metric alarm naming has a 255-char limit and
  alarm-action ARN limits.** Not relevant at our scale; flagged
  as a future concern if the Web ACL grows past ~15 rules.
- **Anomaly detection alarm ships in INSUFFICIENT_DATA for the
  first ~2 weeks.** Visible in the AWS console as orange. Not a
  failure mode — documented in the runbook.
- **WAF cost: ~$13-14/month** at our portfolio volume. Detail
  in the Operational notes section below.

### Operational notes
- The first deploy hit two known categories of friction:
  - **IAM propagation race** — the OIDC role gained
    `wafv2:*` and `cloudfront:*` permissions in the same apply
    that created the WAF and CloudFront resources. Terraform
    parallelizes both, so resource creates can race ahead of
    policy propagation. Self-heals on a re-trigger commit. Same
    pattern as the SNS work documented in the prior commits.
  - **Disallowed punctuation** in resource descriptions. WAFv2
    enforces
    `^[\w+=:#@/\-,\.][\w+=:#@/\-,\.\s]+[\w+=:#@/\-,\.]$` and
    rejected `;` `(` `)` and the em-dash. Caught at first apply,
    fixed in one commit.
- The dev allow-list is a power tool. If a developer pastes
  their home IP CIDR into `terraform.tfvars`, every WAF rule
  except the Allow rule is bypassed for that IP. Treat the
  allow-list as auditable: who, when, why, and rotate aggressively
  when the rationale lapses.

## Alternatives considered

### Where WAF attaches

- **Migrate API Gateway HTTP API to REST API**, then attach WAF
  directly. Heavier refactor — different routing semantics,
  different Lambda integration shape, different response
  transformations, and 3-4× the per-request cost. Rejected for
  the same reason we picked HTTP API in the first place.
- **Front the API with an Application Load Balancer** that
  routes to the Lambdas via the ALB-Lambda integration. ALB
  supports WAF natively. Adds a VPC, security groups, target
  groups, and ~$16/month base cost for ALB itself, plus loses
  HTTP API's request-routing niceties. Rejected as too much
  architectural disruption.
- **Build "WAF-like" middleware in the Lambda handlers.** Custom
  Python doing rate limiting and bad-UA blocking. Loses every
  AWS-managed rule group (the most valuable part of WAF), loses
  the resume signal, and pollutes handler code with security
  logic. Rejected.
- **Skip WAF, document the gap as a known limitation.** Honest
  but doesn't deliver the security engineering layer the project
  set out to build. Rejected.

### Rule set composition

- **Skip Bot Control because it's the most expensive
  managed rule group ($1/mo per million requests in the COMMON
  tier vs $0.60/mo for plain rule groups).** Kept it; for a
  portfolio API with low volume the cost is trivial and the
  signal value is high.
- **Use AWS WAF managed rules only, no custom rules.** Loses
  the bad-UA and rate-limit specificity. Managed rules don't
  rate-limit by IP per path — that's a custom-rule capability.
  Rejected.
- **Only custom rules, no managed groups.** Loses the
  AWS-curated coverage of OWASP categories and IP reputation.
  Rejected.

### Rollout strategy

- **Block-day-one for managed groups too.** Risk of locking out a
  legitimate client request that pattern-matches a managed rule
  signature. The cost of one false-positive lockout exceeds the
  cost of one observation week. Rejected.
- **Permanent Count mode for managed groups.** Ships visibility
  without enforcement, ever. Defeats the point. Rejected after
  the observation week.

### Geo blocking

- **Block CN/RU/KP/IR by default.** Risk of false-positive on
  legitimate users behind VPN exits in those countries. The
  "block-by-default" stance also doesn't reflect actual project
  threat data — we have none yet. Switched to Count-first
  visibility with an opt-in flip.
- **Block-by-default with a much shorter list (e.g., NK only).**
  No clear win. The list either reflects real attack data or it
  doesn't; Count mode generates the data.
- **No geo rule at all.** Losing the visibility into the
  blocked-country traffic patterns means we lose the ability to
  decide later. The Count-mode rule is cheap and informative.

### Rate-limit thresholds

- **Lower default (e.g., 500/5min).** Risks impacting legitimate
  bursts (a developer running tests, a search bot honestly
  enumerating routes). Rejected in favor of higher headroom.
- **Higher sensitive-path threshold (e.g., 1000/5min).** Doesn't
  meaningfully deter scrape-grade traffic. The 300 number was
  chosen so that legitimate single-user traffic stays untouched
  while a scraper trying to mirror the data feed trips quickly.
- **Aggregate-by-forwarded-IP rather than source-IP.** WAF
  supports IP forwarding from CloudFront; not necessary at our
  scale because every request lands at the CloudFront edge first
  and the True-Client-IP is in the X-Forwarded-For chain
  CloudFront sets. WAF's default IP aggregation handles this
  correctly.

### Logging destination

- **Kinesis Firehose to S3 with Athena queries.** Better for
  long-term retention and SQL-style analysis. Adds cost
  (Firehose + S3 + Athena queries) and operational complexity.
  Rejected for a portfolio project. CloudWatch Logs Insights
  covers the analysis use case for free.
- **No logging at all.** Saves $0.50/mo and loses every blocked
  request's body, headers, and rule match. Rejected — the
  observability is the whole point of Count mode.

### Alarming

- **Fixed-threshold drop alarm (`AllowedRequests < N`).** N would
  have to be picked manually from observed traffic, requiring a
  re-tune every time the project's traffic profile changes.
  Rejected in favor of anomaly detection.
- **No drop alarm; just the spike alarm.** Loses the
  over-blocking detection signal — if a rule change accidentally
  starts blocking real users, the only way to find out is a user
  complaint. Rejected.

### Monthly cost (~$13-14)

| Component | Monthly cost |
|---|---|
| Web ACL | $5.00 |
| 4 managed rule groups @ $1/mo | $4.00 |
| 4 custom rules @ $1/mo | $4.00 |
| Request charges (~10K req/mo) | $0.01 |
| WAF CloudWatch Logs | <$0.10 |
| CloudFront distribution | <$1.00 |
| **Total** | **~$14.10** |

Acceptable for the security engineering deliverable.
