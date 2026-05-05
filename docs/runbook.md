# Runbook

Operational procedures for common scenarios. Each procedure includes
the exact commands to run and a verification step.

Assumes `AWS_PROFILE=diamond-iq` and `MSYS_NO_PATHCONV=1` exported.

---

## Design note: ingest re-writes every minute

The ingest Lambda re-writes all qualifying games (Live, Final, Preview)
to DynamoDB every minute it runs, without checking whether anything
changed since the previous tick. Cost at production scale is roughly
$0.05/day under PAY_PER_REQUEST, considered acceptable in exchange for
simpler idempotent semantics: every write is unconditional, status
transitions (Live → Final) overwrite in place by stable PK/SK, and the
TTL is re-stamped on every touch so Final games always live ~7 days
from their last update. A future optimization could conditional-write
only on state change; deliberately deferred.

---

## Redeploy a single Lambda manually

When the CI/CD path is broken or you want to push code changes without
a full Terraform run.

```bash
# 1. Build the deploy zip the same way Terraform does
cd functions/ingest_live_games   # or api_scoreboard
mkdir -p .build/shared
cp -R . .build/
cp -R ../shared/. .build/shared/
cd .build && zip -r ../package.zip . && cd ..

# 2. Push the new code
aws lambda update-function-code \
  --function-name diamond-iq-ingest-live-games \
  --zip-file fileb://package.zip

# 3. Verify the Last Modified timestamp changed
aws lambda get-function \
  --function-name diamond-iq-ingest-live-games \
  --query "Configuration.{Name:FunctionName,LastModified:LastModified,CodeSha256:CodeSha256}"
```

Note: this puts Terraform out of sync with reality. The next
`terraform apply` will detect the drift and roll the function back to
whatever's in the committed source. Use this only as a stop-gap.

---

## Read CloudWatch logs effectively

```bash
# Tail the last N minutes of a Lambda's logs
aws logs tail /aws/lambda/diamond-iq-ingest-live-games --since 10m

# Follow live (Ctrl-C to stop)
aws logs tail /aws/lambda/diamond-iq-ingest-live-games --follow

# Filter to error level only
aws logs tail /aws/lambda/diamond-iq-ingest-live-games --since 1h \
  --filter-pattern '{ $.level = "ERROR" }'

# JSON-shaped queries with CloudWatch Logs Insights:
# Open the AWS console → CloudWatch → Logs Insights → pick the log group, then:
#   fields @timestamp, level, message, games_written, games_failed
#   | filter level = "INFO" and message = "Ingest run complete"
#   | sort @timestamp desc
#   | limit 100
```

API Gateway access logs:

```bash
aws logs tail /aws/apigateway/diamond-iq-api --since 10m
```

---

## Manually trigger an ingest run

Two options.

**Option A — via the AWS CLI** (uses the deployed Lambda code):

```bash
aws lambda invoke \
  --function-name diamond-iq-ingest-live-games \
  --payload '{}' \
  --cli-binary-format raw-in-base64-out \
  /tmp/ingest_response.json

cat /tmp/ingest_response.json
```

**Option B — locally** (uses your working tree's code; useful for
testing changes before deploying):

```bash
uv run python scripts/invoke_ingest_locally.py --table-name diamond-iq-games
```

Verify in DynamoDB:

```bash
aws dynamodb scan --table-name diamond-iq-games --select COUNT
```

---

## Roll back a bad deploy

Terraform state is versioned in S3, so any apply can be rolled back to
the prior state without touching git.

```bash
# 1. List state versions
aws s3api list-object-versions \
  --bucket diamond-iq-tfstate-334856751632 \
  --prefix main/terraform.tfstate \
  --query 'Versions[].{Id:VersionId,Modified:LastModified}' \
  --output table

# 2. Restore the previous version (use the version id from the list above)
aws s3api copy-object \
  --bucket diamond-iq-tfstate-334856751632 \
  --copy-source 'diamond-iq-tfstate-334856751632/main/terraform.tfstate?versionId=<previous-version-id>' \
  --key main/terraform.tfstate

# 3. Apply the now-restored state
cd infrastructure
terraform init -reconfigure
terraform plan       # should show the resources being moved BACK to the prior config
terraform apply

# 4. Revert the offending git commit so future deploys don't re-introduce the bad change
git revert <bad-commit-sha>
git push origin main
```

If the bad change destroyed data (e.g. dropped a DynamoDB item), check
the DynamoDB PITR window:

```bash
aws dynamodb restore-table-to-point-in-time \
  --source-table-name diamond-iq-games \
  --target-table-name diamond-iq-games-restored \
  --restore-date-time "2026-04-25T00:00:00Z"
```

---

## Investigate "no live games" when games should be live

Most often a UTC vs local-date issue (see [ADR 004](adr/004-two-date-ingestion-window.md)). Diagnostic
sequence:

```bash
# 1. Are EventBridge invocations happening?
aws logs tail /aws/lambda/diamond-iq-ingest-live-games --since 5m

#    Expected: one START per minute, plus a JSON summary line.
#    If empty: check the rule
aws events describe-rule --name diamond-iq-ingest-schedule \
  --query "{State:State,Schedule:ScheduleExpression}"

# 2. What is MLB returning for both UTC dates the Lambda queries?
TODAY=$(date -u +%Y-%m-%d)
YESTERDAY=$(date -u -d 'yesterday' +%Y-%m-%d)
curl -s "https://statsapi.mlb.com/api/v1/schedule?sportId=1&date=$YESTERDAY" \
  | python -c "import json,sys; d=json.load(sys.stdin); print(YESTERDAY, sum(1 for date in d.get('dates',[]) for g in date.get('games',[]) if g['status']['abstractGameState']=='Live'), 'live')"
curl -s "https://statsapi.mlb.com/api/v1/schedule?sportId=1&date=$TODAY" \
  | python -c "import json,sys; d=json.load(sys.stdin); print(TODAY, sum(1 for date in d.get('dates',[]) for g in date.get('games',[]) if g['status']['abstractGameState']=='Live'), 'live')"

# 3. What is in DynamoDB right now?
aws dynamodb query --table-name diamond-iq-games \
  --key-condition-expression "PK = :pk" \
  --expression-attribute-values "{\":pk\":{\"S\":\"GAME#$TODAY\"}}" \
  --select COUNT
aws dynamodb query --table-name diamond-iq-games \
  --key-condition-expression "PK = :pk" \
  --expression-attribute-values "{\":pk\":{\"S\":\"GAME#$YESTERDAY\"}}" \
  --select COUNT
```

If MLB shows 0 live for both UTC dates, the system is healthy and
correctly self-throttling. Games visible to a user in their local
timezone may be in `Preview` (haven't started yet) or `Final` (already
ended) at MLB's API even though the user perceives them as "tonight's
games."

---

## Add a new MLB API endpoint to the ingestion

Roughly:

1. **`functions/shared/mlb_client.py`** — add a new `fetch_<thing>()`
   function calling the right URL pattern.
2. **`functions/shared/models.py`** — add a dataclass + `normalize_<thing>()`
   function for the new entity.
3. **`functions/shared/dynamodb.py`** — add `put_<thing>` / `get_<thing>` /
   `list_<thing>s` helpers if the access patterns differ from
   `(PK, SK)`.
4. **`functions/<lambda>/handler.py`** — call the new function in the
   appropriate handler.
5. **`tests/`** — pytest coverage for normalization + happy/sad paths
   on the handler.
6. **PR + CI** — push, watch CI green, deploy auto-fires on merge.

The single-table DynamoDB design means new entities live in the same
table with new PK prefixes — no schema migration. See [ADR 001](adr/001-single-table-dynamodb.md).

---

## Drain the DynamoDB table (test environments only)

There's no native `TRUNCATE`. Two options:

**Option A — destroy/re-create via Terraform** (loses TTL config; clean):

```bash
cd infrastructure
terraform destroy -target=module.dynamodb
terraform apply -target=module.dynamodb
```

**Option B — scan + batch delete** (preserves the table):

```bash
aws dynamodb scan --table-name diamond-iq-games \
  --projection-expression "PK,SK" --output json \
  | python -c '
import json,sys,subprocess
d = json.load(sys.stdin)
for item in d["Items"]:
    subprocess.run(["aws","dynamodb","delete-item","--table-name","diamond-iq-games",
                    "--key", json.dumps({"PK": item["PK"], "SK": item["SK"]})])
'
```

Verify:

```bash
aws dynamodb scan --table-name diamond-iq-games --select COUNT
```

---

## Cost monitoring

```bash
# Current month-to-date spend (via Cost Explorer API)
aws ce get-cost-and-usage \
  --time-period Start=$(date -u +%Y-%m-01),End=$(date -u +%Y-%m-%d) \
  --granularity MONTHLY \
  --metrics "UnblendedCost" \
  --query 'ResultsByTime[].Total.UnblendedCost'
```

Or in the AWS console: **Billing → Cost Explorer → Daily costs**.

Expected baseline (no traffic):
- DynamoDB: $0 (under PAY_PER_REQUEST free tier)
- Lambda: $0 (under 1M invocations + 400k GB-sec free tier)
- API Gateway HTTP API: < $0.01 (no free tier; $1 per million requests)
- CloudWatch Logs: $0 (under 5 GB free tier)
- S3 (state bucket): $0 (under 5 GB free tier)

If MTD spend exceeds **$2** without a traffic explanation, investigate.
The CloudWatch billing alarm at $10 will fire before things get
seriously out of hand.

Common cost surprises:
- CloudWatch log retention set to "Never expire" — should always be
  finite. Our Terraform sets 14 days on every group.
- A misbehaving Lambda in a tight loop. Check
  `aws lambda list-functions ... --query 'Functions[].LastModified'`
  for unexpected recent updates.
- DynamoDB on-demand spike from a runaway client. The CloudWatch
  metric `ConsumedWriteCapacityUnits` will show it.

---

## Daily Content Generation Lambda

The `diamond-iq-generate-daily-content` Lambda produces yesterday's
recaps, today's previews, and two featured matchups by calling Claude
Sonnet 4.6 on Bedrock. Design rationale lives in
[ADR 009](adr/009-daily-content-generation.md).

### What it does

EventBridge fires the Lambda three times daily at 15:00, 16:00, and
17:00 UTC. The 15:00 tick is primary; the 16:00 and 17:00 ticks are
opportunistic fillers — an idempotency check makes them no-ops on a
healthy run, but they recover whatever the first tick missed if a
transient error blocked some of the items.

A successful run takes ~30-90s end-to-end on a normal slate
(15-20 games × ~3-5s per Bedrock call). The Lambda's timeout is 300s
(5 min); the `duration-near-timeout` alarm fires at 240s.

### The five alarms

All five route to the `diamond-iq-alerts` SNS topic and email the
subscriber. State-transition emails arrive within ~1-2 min of the
breach.

#### `diamond-iq-generate-daily-content-bedrock-failures`

- **What triggers it:** the custom metric `BedrockFailures` (sum) is
  greater than 0 in a 1-hour window.
- **What it means:** the Lambda is running but at least one
  InvokeModel call returned an error.
- **First check:** AWS Bedrock service status — invoke the model
  directly from your laptop with a tiny payload and inspect the
  error. If it returns ThrottlingException, you're hitting
  account-level quota. If it returns AccessDenied, IAM is the issue.
- **Second check:** the Lambda's CloudWatch logs filtered by error
  code:
  `aws logs tail /aws/lambda/diamond-iq-generate-daily-content --since 2h --filter-pattern "ThrottlingException"`.
  Each failure logs structured fields including `error_code` and `sk`.
- **Common causes & fixes:**
  - Daily token quota locked at 0 → file an AWS Support ticket;
    this is account-level state, not IAM. See ADR 008.
  - Per-minute rate exceeded → reduce concurrency (currently
    sequential, so this is unlikely).
  - Use-case form not approved → check Bedrock console.
  - Region mismatch → the inference profile must live in
    `us-east-1`; check the `BEDROCK_MODEL_ID` env var on the function.

#### `diamond-iq-generate-daily-content-dynamodb-failures`

- **What triggers it:** the custom metric `DynamoDBFailures` (sum)
  greater than 0 in a 1-hour window.
- **What it means:** Bedrock generated content but DynamoDB rejected
  the write. Worse than Bedrock failures because money was spent on
  tokens that didn't make it to a row.
- **First check:** does the games table still exist?
  `aws dynamodb describe-table --table-name diamond-iq-games`.
- **Second check:** Lambda logs for `DynamoDB put_content_item failed`:
  `aws logs tail /aws/lambda/diamond-iq-generate-daily-content --since 2h --filter-pattern "put_content_item failed"`.
- **Common causes & fixes:**
  - IAM scope changed (someone narrowed the policy) → the content
    Lambda needs `dynamodb:PutItem` on the games-table ARN.
  - Account-level write throttling → unlikely under PAY_PER_REQUEST,
    but check `ConsumedWriteCapacityUnits` and
    `WriteThrottleEvents` for the table.
  - Item too large → the only large field is `text`; check whether
    a recap exceeded 400 KB (DynamoDB item limit). Truncation should
    happen via `max_tokens`; if hit, lower it.

#### `diamond-iq-generate-daily-content-errors`

- **What triggers it:** the AWS-default Lambda `Errors` metric > 0 in
  a 5-min window.
- **What it means:** an unhandled exception escaped the per-item
  try/except. The handler catches Bedrock and DynamoDB errors per
  item, so this only fires on truly unexpected failures —
  ImportError, missing env var, malformed event payload.
- **First check:** the most recent error log line.
  `aws logs tail /aws/lambda/diamond-iq-generate-daily-content --since 30m --format short`
  and look for Python tracebacks.
- **Common causes:** recent deploy broke imports, env var
  `BEDROCK_MODEL_ID` or `GAMES_TABLE_NAME` was unset. Roll back
  the offending commit or fix the env var via Terraform.

#### `diamond-iq-generate-daily-content-duration-near-timeout`

- **What triggers it:** the AWS-default `Duration` metric (max) is
  greater than 240,000 ms (4 min) in a 5-min window. Lambda's
  timeout is 300s.
- **What it means:** something is making each Bedrock call slow, or
  there are way more games than usual.
- **First check:** is Bedrock latency elevated? Look at the
  `ModelInvocationLatency` metric in the
  [Bedrock console](https://us-east-1.console.aws.amazon.com/bedrock/home).
- **Second check:** how many items did the run try to generate?
  `aws logs tail /aws/lambda/diamond-iq-generate-daily-content --since 1h --filter-pattern "Daily content generation complete"`
  and inspect `expected_items`.
- **Common causes:** Bedrock cross-region routing routed to a
  congested region; doubleheader days inflate the Final/Preview
  counts beyond ~25; or `MAX_TOKENS_*` constants were bumped without
  thinking about latency.
- **Mitigation:** if duration is genuinely too high, raise the
  Lambda timeout in `infrastructure/main.tf` and tune the alarm
  threshold accordingly.

#### `diamond-iq-generate-daily-content-invocations-zero`

- **What triggers it:** `Invocations` metric is `<= 0` in a 24-hour
  window.
- **What it means:** EventBridge stopped firing the Lambda. Three
  scheduled triggers should produce 3 invocations per 24h.
- **First check:**
  `aws events list-rules --name-prefix diamond-iq-content` —
  expect three ENABLED rules.
- **Second check:** rule targets are wired:
  `aws events list-targets-by-rule --rule diamond-iq-content-15-utc`.
- **Common causes:** someone disabled an EventBridge rule, the
  `lambda:InvokeFunction` permission for the rule was removed, the
  Lambda was renamed, or the function itself was deleted.

### Manual re-trigger

Use the local invoke script for ad-hoc runs and date backfills:

```bash
# Default: today UTC
python scripts/invoke_generate_locally.py

# Backfill a specific date (e.g., regenerate yesterday's content)
python scripts/invoke_generate_locally.py --date 2026-04-25
```

The script invokes the deployed Lambda via boto3, waits for the
synchronous response, pretty-prints the result, and exits with
status 0 on success or status 1 on Lambda failure. AWS credentials
come from the environment (default boto3 credential resolution).

For one-off invocations without the helper script:

```bash
aws lambda invoke \
  --region us-east-1 \
  --function-name diamond-iq-generate-daily-content \
  --payload '{}' \
  --cli-binary-format raw-in-base64-out \
  --cli-read-timeout 360 \
  /tmp/content-result.json
cat /tmp/content-result.json
```

Expected success output:

```json
{
  "ok": true,
  "date": "2026-04-26",
  "expected_items": 17,
  "items_written": 17,
  "items_skipped": 0,
  "bedrock_failures": 0,
  "dynamodb_failures": 0
}
```

Expected throttled output (current state until AWS Support clears
daily quota):

```json
{
  "ok": false,
  "expected_items": 17,
  "items_written": 0,
  "bedrock_failures": 17,
  "dynamodb_failures": 0
}
```

### Verifying content was generated correctly

Three independent checks, in order of speed:

```bash
# 1. Direct DynamoDB query for the date partition.
aws dynamodb query \
  --region us-east-1 \
  --table-name diamond-iq-games \
  --key-condition-expression "PK = :pk" \
  --expression-attribute-values '{":pk":{"S":"CONTENT#2026-04-26"}}' \
  --projection-expression "SK,content_type,game_pk" \
  --output table

# 2. The API endpoint the frontend uses.
curl https://7x9tjaks0d.execute-api.us-east-1.amazonaws.com/content/today | python -m json.tool

# 3. Frontend visual check. Run the dev server and scroll to the
#    "Today's Featured Matchups" hero — placeholder copy means no
#    content yet, real italicized prose means content is live.
cd frontend && npm run dev
# Then open http://localhost:5173
```

If the API returns empty arrays but DynamoDB has items, the API
Lambda's IAM probably cannot read CONTENT-prefixed items (it should —
same table ARN — but verify via
`aws iam get-role-policy --role-name diamond-iq-api-scoreboard-role --policy-name diamond-iq-api-scoreboard-policy`).

### Common failure modes and recovery

#### Bedrock daily token quota throttle (current state)

- **Symptom:** `bedrock-failures` alarm fires every hour after the
  scheduled tick. Email pair: ALARM at minute ~5, sometimes followed
  by OK if the next tick somehow squeezed through. Lambda summary
  shows `ok=false, bedrock_failures=N, items_written=0`.
- **Action:** none from your side. AWS Support is reviewing the
  daily quota. Until they clear it, the alarm is doing its job by
  truthfully telling you the Lambda is blocked. Do not silence the
  alarm — when the quota clears, the alarm will self-resolve to
  OK and you will see the transition.

#### Quota cleared but Lambda still failing

If the support ticket clears and the Lambda still emits
ThrottlingException, work down this checklist:

```bash
# IAM: does the role have InvokeModel against the right ARNs?
aws iam get-role-policy \
  --role-name diamond-iq-generate-daily-content-role \
  --policy-name diamond-iq-generate-daily-content-policy \
  | grep -A5 Bedrock

# Model access in the Bedrock console:
# https://us-east-1.console.aws.amazon.com/bedrock/home
# → Model access → Anthropic Claude Sonnet 4.6 should be "Access granted".

# Region check — inference profile must live in us-east-1, model id
# must be exactly us.anthropic.claude-sonnet-4-6
aws lambda get-function-configuration \
  --region us-east-1 \
  --function-name diamond-iq-generate-daily-content \
  --query 'Environment.Variables.BEDROCK_MODEL_ID'

# Use-case form: account-level prerequisite, not IAM.
# https://us-east-1.console.aws.amazon.com/bedrock/home → Model access
```

If all four check out and the Lambda still fails, the issue is
likely transient — wait 15 minutes and retry via
`scripts/invoke_generate_locally.py`.

#### DynamoDB write failures

- **Symptom:** `dynamodb-failures > 0`, `items_written < expected`.
  Means we paid for tokens but lost the write.
- **First check:** does the table exist and is it ACTIVE?
  `aws dynamodb describe-table --table-name diamond-iq-games --query 'Table.TableStatus'`
- **Second check:** does the Lambda role still have PutItem on it?
  Should match the policy in `infrastructure/main.tf` —
  `dynamodb:PutItem` on `module.dynamodb.table_arn`.
- **Recovery:** once the underlying issue is fixed, just wait — the
  next scheduled tick will idempotently fill in the missing rows.

---

## WAF + CloudFront

The public entry point is the CloudFront distribution
`https://d17hrttnkrygh8.cloudfront.net`. CloudFront has the WAFv2
Web ACL `diamond-iq-waf` attached. Design rationale lives in
[ADR 010](adr/010-waf-and-rate-limiting.md).

The direct API Gateway URL
`https://7x9tjaks0d.execute-api.us-east-1.amazonaws.com` works
unprotected and is the documented ops-only debugging bypass. Every
real user request goes through WAF.

### The two WAF alarms

Both route to the `diamond-iq-alerts` SNS topic and email the
subscriber.

#### `diamond-iq-waf-blocked-requests-spike`

- **What triggers it:** sum of `BlockedRequests` across all rules >
  1000 in any 1-hour window. Threshold is high deliberately — the
  internet sends background scrape traffic constantly and a
  threshold of "any block at all" would page hourly.
- **What it means:** unusual block volume — either an active
  attack on the API, or a recent rule change is over-blocking
  legitimate traffic.
- **First check:** which rule fired the most in the last hour.
  Open CloudWatch Logs Insights against `aws-waf-logs-diamond-iq`
  and run:
  ```
  fields @timestamp, terminatingRuleId, action, httpRequest.uri, httpRequest.headers.0.value
  | filter action = "BLOCK"
  | stats count() by terminatingRuleId
  | sort count() desc
  ```
- **If `block-known-bad-user-agents` dominates:** likely a real
  scanner targeting the URL. Note the source IPs from
  `httpRequest.clientIp` and decide if the volume warrants a WAF
  rule update or just observe.
- **If a managed rule group (`*-common`, `*-known-bad-inputs`)
  dominates:** look at the matched rules and the request bodies
  causing the match. False-positive lockout is more likely on
  managed groups than on the custom rules.
- **If a rate-limit rule dominates:** someone is hitting the API
  hard. Check the source IPs; if they're known good (e.g., a
  developer's home IP), add to `dev_allow_list_cidrs` in
  `terraform.tfvars`.

#### `diamond-iq-waf-allowed-requests-drop`

- **What triggers it:** `AllowedRequests` falls outside the
  anomaly-detection band trained on the previous ~2 weeks. Most
  often fires on sudden drops, indicating new over-blocking.
- **First check:** did anyone deploy a WAF change recently? Run
  `git log --oneline infrastructure/modules/waf/` and check the
  last few commits. A `count → block` flip on a managed group
  immediately before the alarm is the most likely cause.
- **Recovery:** flip the offending group back to `count` in
  `var.managed_rule_actions`, push, redeploy. Then look at
  Insights for the actual blocked patterns and decide if the rule
  needs an exception.
- **Boot caveat:** for the first ~2 weeks after the alarm was
  created the alarm sits at INSUFFICIENT_DATA — the baseline
  hasn't trained yet. That's expected, not a breach.

### Manual verification commands

Run these from your laptop to confirm the WAF is doing its job.

```bash
# Normal request — should pass.
curl -i https://d17hrttnkrygh8.cloudfront.net/scoreboard/today | head -3
# expect: HTTP/1.1 200 OK + JSON body

# Bad User-Agent — should be blocked at the edge with a 403.
curl -i -A "sqlmap/1.7" https://d17hrttnkrygh8.cloudfront.net/scoreboard/today | head -3
# expect: HTTP/1.1 403 Forbidden + CloudFront error HTML

# Direct API Gateway URL — bypass; should still work.
curl -i https://7x9tjaks0d.execute-api.us-east-1.amazonaws.com/scoreboard/today | head -3
# expect: HTTP/1.1 200 OK + JSON body

# Rate-limit smoke test (20 rapid hits, well under the 2000 ceiling).
for i in $(seq 1 20); do
  curl -s -o /dev/null -w "%{http_code} " https://d17hrttnkrygh8.cloudfront.net/scoreboard/today
done
echo
# expect: twenty consecutive 200s
```

### Investigating with CloudWatch Logs Insights

The WAF log group is **`aws-waf-logs-diamond-iq`** (the
`aws-waf-logs-` prefix is required by AWS, not stylistic). Useful
queries:

```
# All blocked requests in the last hour, with which rule blocked them.
fields @timestamp, action, terminatingRuleId, httpRequest.clientIp,
       httpRequest.uri, httpRequest.headers.0.value as user_agent
| filter action = "BLOCK"
| sort @timestamp desc
| limit 100

# Count-mode hits: rules that WOULD have blocked but were in count.
fields @timestamp, terminatingRuleId, ruleGroupList.0.terminatingRule.ruleId
| filter action = "ALLOW" and ruleGroupList.0.terminatingRule.action = "COUNT"
| stats count() by ruleGroupList.0.terminatingRule.ruleId
| sort count() desc

# Top source IPs by blocked request count.
fields httpRequest.clientIp
| filter action = "BLOCK"
| stats count() by httpRequest.clientIp
| sort count() desc
| limit 20

# Rate-limit-rule trips, by IP.
fields @timestamp, httpRequest.clientIp, httpRequest.uri
| filter terminatingRuleId like /rate-limit/
| stats count() by httpRequest.clientIp
| sort count() desc
```

### Adjusting rate limits

Both rate limits are Terraform variables in `infrastructure/variables.tf`:

- `var.rate_limit_default` (default 2000) — applies to every path
  except `/`.
- `var.rate_limit_sensitive` (default 300) — applies to
  `/content/today` and `/scoreboard/today` only.

To change either, set the value via `terraform.tfvars`:

```hcl
rate_limit_default   = 3000
rate_limit_sensitive = 500
```

Or via env at deploy time: `TF_VAR_rate_limit_default=3000 terraform apply`.

WAF requires a minimum of 100 for rate-based rules; the variable
validation enforces that at plan time.

### Flipping rules from COUNT to BLOCK

Each managed rule group has its own action override in
`var.managed_rule_actions`. Default is `count` for all four. After
the observation week, flip a single group at a time:

```hcl
managed_rule_actions = {
  common_rule_set    = "block"  # was count
  known_bad_inputs   = "count"  # leave for now
  ip_reputation_list = "count"
  bot_control        = "count"
}
```

Push the change. Watch the `BlockedRequests` metric and the email
alarms for the next 24 hours. If something legitimate gets caught,
flip back to `count` and read the Insights output to figure out
which sub-rule fired and why.

**Order of operations** for the rollout:

1. Flip `ip_reputation_list` first — fewest false positives,
   highest signal.
2. Flip `known_bad_inputs` next — exploit signatures rarely match
   legitimate traffic.
3. Flip `common_rule_set` — broadest, most likely to surface a
   false positive on a real client request.
4. Flip `bot_control` last — most aggressive, most likely to
   misclassify a legitimate scraper.

### Geo blocking opt-in

The geo rule runs in COUNT mode by default with
`enable_geo_blocking = false`, so we get visibility on
blocked-country traffic without rejecting anyone. To enforce:

```hcl
enable_geo_blocking = true
```

Push, redeploy, watch the `BlockedRequests` metric. The current
country list is `CN`, `RU`, `KP`, `IR` (variable
`blocked_countries`). Update the list if real attack data
suggests a different cohort.

### Dev IP allow-list

`var.dev_allow_list_cidrs` controls a top-priority Allow rule for
the listed CIDRs — they bypass every other WAF rule. Set this in
`terraform.tfvars` (gitignored), never in source:

```hcl
dev_allow_list_cidrs = ["203.0.113.42/32"]
```

Empty list (the default) means no allow rule exists at all in the
Web ACL — no risk of accidentally allowing more than intended.

### Common failure modes

#### CloudFront 403 on a normal request

If a real user request returns 403 from CloudFront unexpectedly,
the WAF is blocking. Check the `cf-ray` (X-Amz-Cf-Id) header in
the response and grep Insights for that request id.

#### CORS error in browser console

CloudFront forwards the browser's `Origin` header to API Gateway
via the `AllViewerExceptHostHeader` origin request policy. API
Gateway then returns the appropriate
`Access-Control-Allow-Origin` header. If a CORS error appears:

1. Confirm the API Gateway CORS config still includes the
   browser's origin (`var.frontend_origin`).
2. Confirm the cache policy is still `CachingDisabled` — a cached
   response could pin `Access-Control-Allow-Origin` to a single
   origin from a prior request.

#### CloudFront edge serving stale content after a Terraform change

Edge propagation takes 5-15 minutes after `terraform apply`
completes. During the window, some edges may serve the old
config. Wait. Use the AWS Console's CloudFront → Distributions
view to see when status flips from `InProgress` to `Deployed`.

#### Anomaly-detection alarm INSUFFICIENT_DATA

`diamond-iq-waf-allowed-requests-drop` needs ~2 weeks of
`AllowedRequests` data before its band stabilizes. INSUFFICIENT_DATA
during the warmup is expected, not a failure.

---

## Real-time Streaming Pipeline (Option 4)

Score updates flow from a games-table MODIFY to a connected browser
in ~0.7-0.9 s. Pipeline:

```
ingest writes games-table item → DynamoDB Streams MODIFY event
  → diamond-iq-stream-processor Lambda (diff old vs new)
  → query connections-table by-game GSI
  → PostToConnection on the WebSocket API for every subscriber
  → wss frame to the browser → React cache reconciliation
```

Design rationale lives in [ADR 011](adr/011-realtime-streaming-pipeline.md).

### Healthy-pipeline indicators

```bash
# Stream processor invoking on the steady-state ingest cadence
aws cloudwatch get-metric-statistics \
  --region us-east-1 \
  --namespace AWS/Lambda \
  --metric-name Invocations \
  --dimensions Name=FunctionName,Value=diamond-iq-stream-processor \
  --start-time "$(date -u -d '15 minutes ago' '+%Y-%m-%dT%H:%M:%SZ')" \
  --end-time "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" \
  --period 60 --statistics Sum \
  --query "Datapoints[?Sum > \`0\`].[Timestamp,Sum]" --output text

# IteratorAge — should hover near 0 in healthy state
aws cloudwatch get-metric-statistics \
  --region us-east-1 \
  --namespace AWS/Lambda \
  --metric-name IteratorAge \
  --dimensions Name=FunctionName,Value=diamond-iq-stream-processor \
  --start-time "$(date -u -d '15 minutes ago' '+%Y-%m-%dT%H:%M:%SZ')" \
  --end-time "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" \
  --period 60 --statistics Maximum --output text

# Concurrent WebSocket connections
aws cloudwatch get-metric-statistics \
  --region us-east-1 \
  --namespace AWS/ApiGateway \
  --metric-name ConnectCount \
  --dimensions Name=ApiId,Value=cw8v5hucna Name=Stage,Value=production \
  --start-time "$(date -u -d '15 minutes ago' '+%Y-%m-%dT%H:%M:%SZ')" \
  --end-time "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" \
  --period 60 --statistics Maximum --output text
```

### The three Option-4 alarms

#### `diamond-iq-stream-processor-errors`

- **Trigger:** AWS-default Lambda `Errors` > 0 / 5-min window.
- **Means:** an unhandled exception escaped per-record handling.
  The handler catches Bedrock-style failures and individual
  PostToConnection failures per record, so this only fires on
  truly unexpected failures (ImportError, missing env, malformed
  Streams event, DynamoDB throttling exceeding retries).
- **First check:** the latest exception trace.
  `aws logs tail /aws/lambda/diamond-iq-stream-processor --since 30m --format short`
  and look for `[ERROR]` Python tracebacks.
- **Common causes:** the games-table stream ARN env var is wrong
  (post-redeploy regression), or DynamoDB connections-table got
  destroyed (verify table exists), or PostToConnection is being
  rate-limited by a misbehaving client.

#### `diamond-iq-stream-processor-iterator-age`

- **Trigger:** `IteratorAge` (max) > 60_000 ms / 5-min window.
- **Means:** the processor is reading from the stream slower than
  records arrive. Sustained lag suggests a record taking >1s to
  fan out — usually a slow PostToConnection call cascading.
- **First check:** correlate with PostToConnection latency in the
  stream-processor logs (per-record `outcomes` field).
- **Common causes:** WebSocket clients with bad backpressure
  (rare in browsers; possible if a misbehaving CLI tool is
  connected), or a poison record bisecting repeatedly with
  `bisect_batch_on_function_error=true`.
- **Recovery:** if a poison record is suspected, look at the
  stream-processor's `error` counter in recent batches. A record
  that appears in >2 successive `error: 1` summary logs is a
  candidate for a manual `aws lambda update-event-source-mapping
  --maximum-record-age-in-seconds` to evict it from the shard.

#### `diamond-iq-ws-connections-high`

- **Trigger:** WebSocket `ConnectCount` > 1000 / 5-min window.
- **Means:** more than 1000 concurrent connections — well past
  expected portfolio scale. Either viral traffic (good) or a bot
  storm (bad).
- **First check:** `aws apigatewayv2 get-stage --api-id cw8v5hucna
  --stage-name production --query "ConnectionCount"`.
- **Recovery options:** rate-limit `$connect` via API Gateway
  throttle config, or implement a Lambda authorizer that admits
  N connections per source IP per minute.

### Manual end-to-end test

Verifies the full pipeline from a synthetic DynamoDB MODIFY to a
WebSocket frame on a connected client. Useful after a deploy.

```bash
# 1. Pick a game_pk that exists on today's UTC date partition.
DATE_STR="$(date -u +%Y-%m-%d)"
aws dynamodb query --region us-east-1 --table-name diamond-iq-games \
  --key-condition-expression "PK = :pk" \
  --expression-attribute-values "{\":pk\":{\"S\":\"GAME#${DATE_STR}\"}}" \
  --projection-expression "game_pk" --max-items 1 \
  --query "Items[0].game_pk.N" --output text
# → some game_pk like 822825
```

```python
# 2. From a Python REPL or `python -c`, with `pip install websockets`.
import asyncio, json, subprocess, time
import websockets

URL = "wss://cw8v5hucna.execute-api.us-east-1.amazonaws.com/production"
GAME_PK = 822825  # from step 1
DATE_STR = "2026-04-27"

async def main():
    async with websockets.connect(URL) as ws:
        await ws.send(json.dumps({"action": "subscribe", "game_pk": GAME_PK}))
        await asyncio.sleep(2)
        # Force a MODIFY by updating away_score on the targeted row.
        subprocess.run([
            "aws", "dynamodb", "update-item",
            "--region", "us-east-1",
            "--table-name", "diamond-iq-games",
            "--key", json.dumps({"PK": {"S": f"GAME#{DATE_STR}"}, "SK": {"S": f"GAME#{GAME_PK}"}}),
            "--update-expression", "SET away_score = :s",
            "--expression-attribute-values", json.dumps({":s": {"N": "42"}}),
        ], check=True)
        msg = await asyncio.wait_for(ws.recv(), timeout=15.0)
        print(json.loads(msg))

asyncio.run(main())
```

Expected: a `score_update` payload arriving in <2 seconds.

### Common failure modes

#### WebSocket handshake returns 403

- API Gateway WebSocket stage is missing or unhealthy.
- `aws apigatewayv2 get-stages --api-id cw8v5hucna` should return
  one stage named `production`.
- If empty: terraform apply must not have completed; retrigger CI.

#### Subscribe succeeds but no updates arrive

- The stream-processor Lambda is running but its batch returns
  `sent: 0` with `skipped: N`.
- Most common cause: the targeted game's MODIFY event diff didn't
  include any of the push-list fields (only `ttl` changed, e.g.).
  Re-run with a real score change and watch the `outcomes` log line.
- Less common: the stream-processor's IAM doesn't permit
  `dynamodb:Query` on the by-game GSI, or `execute-api:ManageConnections`
  on the WebSocket API. Check the role policy.

#### 410 Gone in stream processor logs

- Working as designed. The processor encountered a stale
  connection (e.g., a client whose tab closed without sending
  `$disconnect`) and is cleaning up the connection's rows. The
  TTL on the connections table catches anything the 410 path
  misses within 4 hours.

#### Out-of-order subscribe/unsubscribe in client

- Documented limitation. WebSocket → API Gateway → Lambda is
  asynchronous; bursts of messages microseconds apart can
  process out of order.
- Frontend remediation: debounce client-side. A 200 ms debouncer
  around the subscribe/unsubscribe calls is enough for any
  realistic UI pattern.

### First-time-deploy notes

Option 4 deploys in a fresh account require **2-3 retrigger
commits**. The pattern:

1. **`dynamodb:CreateTable` IAM race** when the OIDC role's
   DynamoDB scope broadens. Self-heals on retrigger.
2. **`apigateway:UpdateAccount` + `iam:PassRole` for the
   account-level CloudWatch Logs role.** One-time-per-account
   prerequisite for v2 WebSocket access logs. Catalogued; not a
   race.
3. **`lambda:TagResource` on the event-source-mapping ARN
   class.** AWS provider 5.x applies default tags to event source
   mappings, requiring `lambda:TagResource` on a different ARN
   shape than the function-level grant. Once granted, an IAM
   propagation race typically requires one more retrigger.

These are project-known prerequisites, captured in OIDC role
policy commits as they're hit. Future Option-N work in this account
will not pay the cost again.

## Known gotchas

### Multi-file Lambda packages

When a Lambda function imports sibling modules from the same package,
the zip is flattened at the root by the Lambda module, so relative
imports (`from .X import Y`) fail at runtime with
`Runtime.ImportModuleError: attempted relative import with no known
parent package`. Use absolute imports (`from X import Y`) and add
`sys.path.insert(0, dirname(__file__))` at the top of `handler.py`
for pytest compatibility. Single-file Lambdas don't hit this; only
multi-module packages. (Surfaced during Phase 5E `api_players`
deploy; see commit `984c73c`.)

Also note: avoid module names that collide with PyPI dev-deps.
`responses` shadows the popular `responses` mocking library and
breaks pytest collection. Renamed to `api_responses.py` to dodge
this.
