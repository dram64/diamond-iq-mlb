# ADR 008 — Bedrock Claude access via cross-region inference profile

## Status
Accepted

## Context
Phase 9 introduces a daily Lambda that calls Claude on Amazon Bedrock
to generate editorial content (recap, per-game previews, featured
matchups). Three things needed to be settled:

1. Which model
2. How to address the model in IAM and at runtime
3. How to scope the Lambda's permissions

### 1. Which model

The Bedrock catalog in `us-east-1` exposes 17 active Claude models
spanning the Haiku, Sonnet, and Opus tiers. Pricing per 1M tokens
(in / out):

| Model | Input | Output |
| --- | --- | --- |
| Haiku 4.5 | $1.00 | $5.00 |
| Sonnet 4.6 | $3.00 | $15.00 |
| Opus 4.7 | $15.00 | $75.00 |

For our daily token budget (~351 k input / ~195 k output / month),
the monthly costs are $1.33, $3.98, and $19.90 respectively.

### 2. How to address it

Newer Claude generations on Bedrock (the entire 4.x line)
**cannot be invoked via the bare foundation-model id**. Direct invocation
returns:

> `ValidationException: Invocation of model ID
> anthropic.claude-sonnet-4-6 with on-demand throughput isn't supported.
> Retry your request with the ID or ARN of an inference profile that
> contains this model.`

Bedrock requires a *cross-region inference profile* — an AWS-managed
indirection that load-balances InvokeModel calls across foundation
model copies in multiple regions. For our model the profile id is
`us.anthropic.claude-sonnet-4-6`, with ARN
`arn:aws:bedrock:us-east-1:<account>:inference-profile/us.anthropic.claude-sonnet-4-6`,
and it routes to foundation models in `us-east-1`, `us-east-2`, and
`us-west-2`.

### 3. IAM scoping

Bedrock checks `bedrock:InvokeModel` on **both** the inference profile
ARN AND the underlying foundation-model ARNs in every region the
profile may route to. A policy that grants only the profile ARN fails
at routing time with `AccessDenied`. A policy that grants only the
foundation-model ARNs fails because the API call goes through the
profile.

## Decision

### Model
Use `us.anthropic.claude-sonnet-4-6` for editorial content generation.
At ~$4/month for our volume, the prose quality (vs Haiku) is worth
the difference for public-facing copy. Opus is overkill.

### IAM policy
The daily-content Lambda's role grants `bedrock:InvokeModel` against
both ARN classes:

```hcl
resources = [
  # Inference profile (the address callers use)
  "arn:aws:bedrock:us-east-1:<account>:inference-profile/us.anthropic.claude-sonnet-4-6",

  # Foundation models the profile may route to (cross-region)
  "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-sonnet-4-6",
  "arn:aws:bedrock:us-east-2::foundation-model/anthropic.claude-sonnet-4-6",
  "arn:aws:bedrock:us-west-2::foundation-model/anthropic.claude-sonnet-4-6",
]
```

The Lambda role is **separate** from the existing ingest and API roles.
Bedrock access doesn't bleed into Lambdas that don't need it.

### Account-level prerequisite
Before any IAM-scoped role can invoke an Anthropic model on a fresh
AWS account, the Bedrock console requires submission of an
**Anthropic use-case details form** (project description, intended
use, contact). Approval propagates within ~15 minutes. Until then,
every InvokeModel call returns:

> `ResourceNotFoundException: Model use case details have not been
> submitted for this account.`

This is account-level state, not IAM state. Documented here because
the error message is misleading — IAM policies can be perfect and the
call will still fail until the form clears.

## Consequences

### Positive
- The daily-content Lambda works against the highest-quality
  cost-reasonable Claude model available.
- IAM scoping is tight: only the daily-content Lambda can invoke
  Claude, and only against this one model. Adding a second Claude
  model later means an explicit policy update.
- Cross-region routing gives the system inherent resilience to
  single-region Bedrock incidents.

### Negative
- Two distinct ARN forms to remember (profile and foundation model).
  The Terraform module documents both inline so it's not a footgun.
- Foundation-model ARNs are partition-style (no region account id),
  which trips intuition when someone expects normal account-scoped
  resource ARNs.
- Cross-region inference can spend an extra ~50ms on long-tail calls
  versus a same-region direct invocation. For a daily background
  Lambda that's irrelevant.

### Operational notes
- If a new model version is added later (e.g. Sonnet 4.7), the
  inference-profile id, the profile ARN, and the foundation-model ARNs
  all change together. Update the Terraform locals in one place.
- The use-case form is per-account, one-time. If we ever set up a
  separate dev account, that account needs its own form submission.
