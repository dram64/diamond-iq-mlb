# ADR 002 — Vendored shared code over Lambda Layers

## Status
Accepted

## Context
Both Lambda functions (`ingest_live_games`, `api_scoreboard`) import
from `functions/shared/` (MLB client, models, DynamoDB helpers, JSON
logger). Two ways to get that shared code into the deploy artifact:

1. **Lambda Layer** — package `shared/` as a layer, attach the layer
   to each function. Decouples shared from function code; the layer
   has its own version lifecycle.
2. **Vendoring** — copy `shared/` into each function's deploy zip at
   build time. Each function ships a self-contained zip.

## Decision
Vendor `shared/` into each Lambda zip at Terraform plan time using
`archive_file` `dynamic "source"` blocks (see [ADR 006](006-archive-file-dynamic-source.md)).

## Consequences

### Positive
- Simpler Terraform: no separate layer resource, no version-pinning
  table, no `aws_lambda_layer_version_permission`.
- Atomic deploys: a code change in `shared/` produces new zips for
  both functions in one apply, with matching content hashes. No
  possibility of one function being on layer v3 while the other is
  on v2.
- Local testing is identical to production — `pythonpath = ["functions"]`
  in `pyproject.toml` lets pytest import `from shared.X import Y` the
  same way the deployed Lambda does.
- No layer cold-start overhead. (Layers are zipped, downloaded, and
  unpacked separately by the Lambda runtime.)

### Negative
- Each function's zip is slightly larger (the shared package gets
  duplicated). At our size, ~30 KB per zip — irrelevant. Layers
  matter for binary deps like `numpy` (tens of MB).
- If `shared/` ever grows large (e.g. a vendored AWS SDK), this
  decision should be revisited.

### When to revisit
- Shared code exceeds 5 MB.
- Number of Lambdas grows past ~5 (at which point version drift
  concerns from layer-versioning are outweighed by deploy-zip size).
- We add a third-party dependency that's heavy enough that downloading
  it twice on cold start hurts.
