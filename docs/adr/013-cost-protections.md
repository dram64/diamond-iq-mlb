# ADR 013 — Cost-runaway protections

## Status
Accepted

## Context
The project has shipped 8 Lambdas, several DynamoDB partitions, a
WebSocket pipeline, an Anthropic Bedrock integration, and a fan-out
stream processor. Any of those — through a misconfigured trigger,
a recursive loop, or a code bug — could spike invocation count and
generate unbounded cost in minutes.

A $50/month AWS Budgets hardcap is configured manually in the
console with a `BudgetExceededDenyAll` IAM policy auto-applied at
100% (one-time IAM-role bootstrap is awkward to express via
Terraform from a fresh account). That is the **floor** — actual
billing for the month never exceeds $50 — but it's a blunt
instrument that cuts every IAM call after the spike has already
happened.

This ADR adds **defense-in-depth** between normal operations and
the budget hardcap. Five layers, each catches a different failure
mode before it reaches the budget:

1. **Per-Lambda concurrency reservations** cap simultaneous
   in-flight invocations of any single function.
2. **DynamoDB Streams retry/age caps + DLQ** prevent a poison
   record from re-invoking the stream processor forever.
3. **Per-function runaway-invocation alarms** notify on
   anomalous invocation count well before the budget alarm.
4. **Account-wide concurrent-executions alarm** catches
   concurrency spikes that escape per-function reservations.
5. **Lambda Recursive Loop Detection** terminates self-recursive
   invocation chains at the AWS service layer.

## Decision

### 1. `reserved_concurrent_executions` (deferred — account quota too low)

The intended protection: a per-function reservation of 10 caps
simultaneous in-flight invocations of any single Lambda. A
runaway trigger spiking to 1000/sec would process at most 10 at
a time; the other 990/sec become throttled invocations (HTTP 429
from `Lambda:Invoke`); the trigger source backs off.

**Blocker discovered at apply time:** the account's
`ConcurrentExecutions` quota is **10**, not the AWS default of
1000:

```bash
$ aws lambda get-account-settings --query AccountLimit
{
    "ConcurrentExecutions": 10,
    "UnreservedConcurrentExecutions": 10,
    ...
}
```

AWS requires `UnreservedConcurrentExecutions >= 10` at all times.
With the account ceiling also at 10, the math has no room for
ANY reservation — `(quota) - (sum of reservations) >= 10`
collapses to `sum of reservations <= 0`. AWS returns
`InvalidParameterValueException` on the first PutFunctionConcurrency
call.

**Resolution path:** file an AWS Support ticket to raise
`ConcurrentExecutions` from 10 to 100 (or higher). Once raised,
flip the lambda module's default for
`reserved_concurrent_executions` from `-1` (unreserved) to `10`
in a single-line commit, and the next apply lands the
reservations on all 8 functions. **Same kind of service-team-
controlled quota that gated Bedrock — not an architecture or
IAM problem.**

Until then, the other four protections in this ADR (DLQ + retry
caps, runaway alarms, account-wide concurrency alarm, recursive
loop detection) remain active. The account-wide
ConcurrentExecutions alarm at 50 won't fire because the account
ceiling is below it; it becomes meaningful only after the quota
increase, at which point it's the per-function reservation's
backstop.

The variable lives in `infrastructure/modules/lambda/variables.tf`.
After quota increase, the change is:

```hcl
variable "reserved_concurrent_executions" {
  type    = number
  default = 10  # was -1
}
```

Re-examine if any function's parallelization or shard count
exceeds 10 in the future — the stream-processor's
`parallelization_factor` is currently 10 and would sit exactly
at the reservation.

### 2. DynamoDB Streams retry / age caps + DLQ

The event source mapping for the stream processor previously had
the AWS defaults: `maximum_retry_attempts = -1` (infinite) and
`maximum_record_age_in_seconds = -1` (no max age). A poison record
under those defaults would re-invoke the Lambda forever — exactly
the runaway shape we want to bound.

New configuration:

- `maximum_retry_attempts = 5` — after 5 failed retries the record
  is shipped to the DLQ.
- `maximum_record_age_in_seconds = 3600` — records older than 1
  hour are also shipped to the DLQ. Catches a long-stuck record
  that hasn't yet hit retry 5 because invocations are slow.
- `bisect_batch_on_function_error = true` — already set; halves
  the batch on retry so a single bad record doesn't poison the
  whole batch.
- `destination_config.on_failure` → `aws_sqs_queue.stream_processor_dlq`
  — the DLQ that catches the rejected records.

The DLQ itself:

- name `diamond-iq-stream-processor-dlq`
- visibility timeout 300s (room for a future redrive consumer)
- message retention 14 days (long enough to investigate)
- SQS-managed SSE for at-rest encryption

The stream-processor execution role gains a single `sqs:SendMessage`
grant scoped to the DLQ ARN. Queue access policies are not
consulted on the destination-config delivery path.

### 3. Per-function runaway-invocation alarms

8 new CloudWatch metric alarms, one per Lambda, all routed to the
existing `diamond-iq-alerts` SNS topic:

| Function | Alarm name |
|---|---|
| `diamond-iq-ingest-live-games` | `…-runaway-invocations` |
| `diamond-iq-api-scoreboard` | `…-runaway-invocations` |
| `diamond-iq-generate-daily-content` | `…-runaway-invocations` |
| `diamond-iq-test-bedrock` | `…-runaway-invocations` |
| `diamond-iq-stream-processor` | `…-runaway-invocations` |
| `diamond-iq-ws-connect` | `…-runaway-invocations` |
| `diamond-iq-ws-disconnect` | `…-runaway-invocations` |
| `diamond-iq-ws-default` | `…-runaway-invocations` |

Threshold: `Invocations > 10_000` over a 1-hour window. For
context: ingest-live-games runs every minute = ~60 invocations/hr.
Steady-state every function combined produces well under 500
invocations/hour. 10000/hr is ~20× peak and only crosses for a
genuine runaway.

### 4. Account-wide ConcurrentExecutions alarm

One additional alarm on the account-level
`AWS/Lambda#ConcurrentExecutions` metric, threshold 50, 5-minute
window. Catches:

- A future Lambda that ships without `reserved_concurrent_executions`.
- A regression that drops the reservation on an existing function.
- A genuine cross-function concurrency spike (e.g., API and
  WebSocket and stream-processor all peaking simultaneously).

50 is well above expected peak. AWS's account-wide concurrency
default is 1000; we're alarming far below that to give an early
warning rather than waiting for AWS's hard ceiling.

### 5. Lambda Recursive Loop Detection — verified

AWS Lambda Recursive Loop Detection is enabled by default for all
functions created after August 2023. We verified all 8 Lambdas
show `RecursiveLoop: Terminate` and document the verification
here. No active configuration required.

The verification command:

```bash
for fn in diamond-iq-ingest-live-games diamond-iq-api-scoreboard \
          diamond-iq-generate-daily-content diamond-iq-test-bedrock \
          diamond-iq-stream-processor diamond-iq-ws-connect \
          diamond-iq-ws-disconnect diamond-iq-ws-default; do
  echo "$fn: $(aws lambda get-function-recursion-config \
    --region us-east-1 --function-name "$fn" --query RecursiveLoop --output text)"
done
```

If any function ever shows `Allow`, run:

```bash
aws lambda put-function-recursion-config \
  --region us-east-1 \
  --function-name <name> \
  --recursive-loop Terminate
```

## Consequences

### Positive
- **Five independent guardrails** between normal operation and
  the budget hardcap. Each catches a different failure mode.
- **Quantified blast radius.** Even a worst-case recursive loop
  hitting Lambda's quotas now caps at: 10 concurrent × 5 retries
  × all 8 functions × ~5s per invocation ≈ 2000 invocations/min
  per function maximum. At Lambda's $0.20/1M invocations + $0.000016/100ms,
  that's roughly $0.50/hour of compute even in the worst case.
- **DLQ gives operators a record** of what tripped the protection,
  for post-mortem investigation.
- **Account-wide concurrency alarm closes the gap** for future
  Lambdas that might ship without their own reservation.
- **No application code changes.** All protection lives at the
  infrastructure layer; handlers don't need to know.

### Negative
- **Reserved concurrency consumes account quota.** 8 functions ×
  10 reservations = 80 concurrency units locked to this project.
  AWS's default account quota is 1000; we're using 8% of it.
  Negligible for a single-account portfolio project; a
  consideration for an account hosting many projects.
- **DLQ adds a new resource that can also accumulate cost.** SQS
  PAY_PER_REQUEST charges per-message; at 14-day retention, a
  flood of poison records could fill the queue. We don't currently
  alarm on `ApproximateNumberOfMessagesVisible`. Documented as a
  future polish item — set a `> 100` alarm if any DLQ message ever
  arrives.
- **The runaway-invocation threshold (10k/hr) is intentionally
  high.** A subtler runaway (say 9k/hr sustained over 24 hours)
  wouldn't trip this alarm but would still spend ~$5 of compute.
  The budget hardcap remains the floor for that class of slow
  drip.
- **Account-wide concurrency at 50 is conservative for the v1
  scale**, deliberately. Tightening it as the project grows will
  require revisiting if real load ever pushes near that number.

### Operational notes
- The DLQ is empty under normal operations. A non-empty DLQ
  always represents a real problem — a poison record, a stuck
  consumer, or a bug in the diff function. Investigate by
  receiving from the queue and inspecting the wrapped record.
- Reserved concurrency interacts with on-demand throttling:
  invocations beyond the reservation receive 429s and the
  invoking service must back off. For our DynamoDB Streams
  trigger, AWS handles this transparently — bursts beyond 10
  concurrent stream-processor invocations get queued at the
  shard iterator and resume when concurrency frees up.
- The $50 budget hardcap is configured in the AWS console at
  Billing → Budgets and applies the
  `AWSBudgetActionsExceededDenyAll` IAM policy at 100%
  utilization. Re-applying it cleanly via Terraform requires the
  one-time `aws iam create-service-linked-role
  --aws-service-name budgets.amazonaws.com` call plus the budget
  action role bootstrap; we accept the manual configuration cost
  in exchange for not bootstrapping IAM service-linked roles
  through CI.

## Alternatives considered

### Per-function reservation
- **No reservation.** Default behavior; allows unbounded
  per-function concurrency up to the account ceiling. Rejected.
- **`reserved_concurrent_executions = 1`.** Aggressively tight
  but breaks headroom for ws-default's modest concurrent message
  rate during normal use. Rejected.
- **`reserved_concurrent_executions = 100`.** Ceiling so high
  it doesn't actually constrain a runaway. Rejected.

### Stream retry caps
- **Keep the AWS defaults (-1 / -1).** Pure runaway shape if a
  poison record exists. Rejected.
- **`maximum_retry_attempts = 0`.** Any record-level error
  immediately drops to DLQ. Too aggressive — transient errors
  (DynamoDB throttling, brief PostToConnection 5xx) are
  legitimately retryable. Rejected.
- **`maximum_record_age_in_seconds = 86400` (1 day).** Trades
  cost ceiling for transient resilience. Rejected — 1 hour is
  enough for any legitimate retry; beyond that the record is
  almost certainly poison.

### Per-function vs per-batch alarms
- **Single account-level Invocations alarm.** Loses per-function
  granularity at investigation time. Rejected.
- **Multi-window alarms (5-min + 1-hr + 24-hr).** Better dynamic
  range but multiplies alarm count by 3×. Rejected for v1; the
  budget hardcap covers the slow-drip case.

### Budget hardcap location
- **Terraform-managed budget action.** Requires bootstrapping
  the budget actions service-linked role and a delegating IAM
  role. Possible but awkward from a fresh account; rejected for
  v1, manually configured in the console instead.

## Forward references

- A `> 100 messages` alarm on the DLQ would close the
  cost-from-DLQ-fill gap. Future polish.
- Tightening the per-function reservation from 10 to a measured
  P99 + headroom value, once we have a longer baseline. Future
  polish.
- The same protections apply automatically to any future Lambda
  added through the existing `modules/lambda` module — the
  `reserved_concurrent_executions` default is wired at the module
  level, not per-instantiation.
