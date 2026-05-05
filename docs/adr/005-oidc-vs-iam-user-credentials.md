# ADR 005 — OIDC over long-lived IAM user credentials for CI/CD

## Status
Accepted

## Context
GitHub Actions needs AWS credentials to apply Terraform on push to
main. Two options:

1. **IAM user with access keys**, stored as GitHub Secrets
   (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`).
2. **OIDC federation** — GitHub mints a short-lived JSON Web Token per
   workflow run; AWS verifies it via an `aws_iam_openid_connect_provider`
   trust and returns a temporary STS session.

## Decision
Use **OIDC**. The Terraform main stack creates the OIDC provider for
`token.actions.githubusercontent.com` and an IAM role
`diamond-iq-github-deploy` that trusts that provider with a `sub`
condition scoped to `repo:dram64/diamond-iq:*`. The workflow uses
`aws-actions/configure-aws-credentials@v4` to assume the role.

## Consequences

### Positive
- **Zero long-lived credentials** anywhere. Nothing to leak in a
  GitHub Secret, nothing to rotate quarterly, nothing in a credential
  CSV that gets accidentally opened in an editor.
- Each workflow run gets its own STS session with a unique
  `role-session-name` (`github-actions-${{ github.run_id }}`).
  CloudTrail attributes every API call to a specific run.
- The trust policy can be tightened over time without changing any
  secret material — e.g. restricting to `repo:dram64/diamond-iq:ref:refs/heads/main`
  to block PR-branch deploys.
- AWS-recommended pattern; well-documented and widely supported.

### Negative
- More moving parts to set up: OIDC provider resource, role with
  trust policy, role with deploy policy. Bootstrap is more involved
  than just pasting an access key into GitHub Secrets.
- The deploy role's permissions need to be scoped carefully — too
  broad and a compromised workflow can do damage; too narrow and
  Terraform refresh fails. Two such failures were caught during
  Phase 7 setup (logs:DescribeLogGroups requires a wildcard resource;
  iam:GetOpenIDConnectProvider was missing from initial scope).
- Debugging trust failures requires reading STS error messages
  carefully. Common mistakes: missing `sub` claim, wrong audience
  (`sts.amazonaws.com`), missing `id-token: write` permission in the
  workflow.

### When to revisit
- If we ever need to deploy from an environment that isn't a GitHub
  Actions runner (e.g. a CircleCI job), we'd add another OIDC
  provider trust, not fall back to IAM user keys.
- If we add a second AWS account (per ADR 007), the OIDC role lives
  in that account; the trust policy is the same shape.
