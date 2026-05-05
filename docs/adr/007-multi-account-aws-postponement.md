# ADR 007 — Postpone multi-account AWS Organizations setup

## Status
Accepted

## Context
AWS best practice for production systems is to separate environments
(dev / staging / prod) into distinct AWS accounts under an
Organization, with cross-account IAM and centralized logging. This
limits the blast radius of any single mistake or breach: a `terraform
destroy` in dev can't accidentally delete prod resources.

The cost: setting up Organizations, an account factory, cross-account
roles, SSO, central CloudTrail/Config aggregation, and a billing
hierarchy is a substantial chunk of work — easily multiple days for a
single-developer project.

## Decision
For now, **operate in a single AWS account** with one environment
(`prod`). Tag every resource with `Environment = "prod"` so future
multi-account migration has clean filtering. Defer the multi-account
split until at least one of these is true:

- Multiple developers regularly apply Terraform.
- The cost of an accidental destroy is more than ~1 day's
  rebuild effort.
- Compliance or auditing requirements force account-level isolation.

## Consequences

### Positive
- Drastically simpler bootstrap. One account, one OIDC provider, one
  state bucket, one set of IAM roles to reason about.
- No cross-account IAM debugging in the early stages, when most
  errors are about the application code, not the cloud topology.
- The training/sandbox account this project lives in already has
  natural blast-radius isolation — it's not the user's primary AWS
  account.

### Negative
- A `terraform destroy` (intentional or accidental) takes everything
  down at once. Mitigation: PITR on DynamoDB, S3 versioning on the
  state bucket, billing alarms, scoped deploy IAM role.
- "dev/staging/prod" environment promotion is not a thing yet. To
  test changes safely, run them locally with moto-mocked DynamoDB or
  via the local invoke scripts before pushing.
- When we do add a second account, `Environment` tag values diverge
  and some resource names will need to incorporate the env (today
  the table is just `diamond-iq-games`, not `diamond-iq-games-prod`).

### When to revisit
- A second contributor joins the project who isn't the account owner.
- We have paying users (or any user-data with regulatory weight).
- We hit a production-impacting incident caused by single-account
  blast radius.

### Migration sketch (when the time comes)
1. Create AWS Organization with the current account as management.
2. Create new accounts: `diamond-iq-prod`, `diamond-iq-dev`.
3. Move the existing resources to the prod account (likely via fresh
   bootstrap + Terraform apply in the new account, then DNS / API
   endpoint cutover).
4. Add a `var.environment` workspace dimension to the main stack so
   dev and prod share the same module code with different tfvars.
