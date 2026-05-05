# Contributing

## Dev environment

See [docs/setup.md](docs/setup.md) for the full first-time walkthrough.
TL;DR:

```bash
git clone https://github.com/dram64/diamond-iq.git
cd diamond-iq
uv sync
uv run pytest
```

For the frontend:

```bash
cd frontend
npm install
npm run dev
```

## Coding standards

### Python (`functions/`, `tests/`, `scripts/`)
- Python 3.12, pinned in `.python-version`
- Lint: `ruff check .` (rules in `pyproject.toml`)
- Format: `black .` (line length 100)
- Tests: `pytest`. New code adds tests; tests live under `tests/<package>/`
  mirroring the source tree.
- Type hints on all public functions. `from __future__ import annotations`
  at the top of every module.
- Imports: stdlib first, then third-party, then local (`from shared.X import Y`).
  Ruff's isort rule enforces this.
- No `# type: ignore` without a comment explaining why.

### Terraform (`infrastructure/`)
- `terraform fmt -recursive` clean
- `terraform validate` clean (in both `infrastructure/` and `infrastructure/bootstrap/`)
- Resources scoped by ARN pattern wherever possible (project-name prefix)
- Default tags applied via the provider, not per-resource
- Module boundaries: each module has its own `main.tf`, `variables.tf`,
  `outputs.tf`. No bare `terraform.tfvars` checked in.
- Sensitive defaults flagged in the variable's `description`

### YAML (`.github/workflows/`)
- Action references pinned to commit SHAs (not `@main`, `@v4`, etc.).
  Supply-chain attacks on tagged versions are real.
- `permissions:` blocks set the minimum required at workflow level.
- `concurrency:` group set on every workflow.

### Markdown (`README.md`, `docs/`)
- One sentence per line in long-form docs is fine but not required.
- Code blocks tagged with their language for syntax highlighting.

## Commit messages

Imperative mood, present tense, ≤72-character subject. Body wrapped
at 80 if present. Examples:

> `Fix ingestion to query both today and yesterday UTC dates for live game coverage across timezone boundaries`

> `Grant deploy role logs:DescribeLogGroups and OIDC-provider read perms for terraform refresh`

> `Add Terraform main stack: DynamoDB, Lambdas, API Gateway, EventBridge, OIDC`

No emoji prefixes, no Conventional Commits formality. Just clear
prose. The body should explain the *why*; the diff already shows the
what.

## PR process

1. Branch from `main`. Branch naming is up to you; my convention is
   `topic/short-description`.
2. Local checks pass: `uv run pytest`, `uv run ruff check .`,
   `uv run black --check .`, `terraform fmt -recursive -check`.
3. Open the PR against `main`. The template in
   [.github/PULL_REQUEST_TEMPLATE.md](.github/PULL_REQUEST_TEMPLATE.md)
   prompts the right info.
4. CI runs automatically. Lint, test, and Terraform validate must
   pass. Path filters mean frontend-only changes don't run backend CI.
5. Self-review the diff before requesting review (catches the
   embarrassing typos I'd otherwise notice 5 minutes after a merge).
6. After merge, the deploy workflow auto-applies infrastructure changes
   to AWS via OIDC. Watch the **Deploy summary** step in the workflow
   run for the API endpoint and resource names.

## Architecture decisions

Significant decisions live in [docs/adr/](docs/adr/) as Architecture
Decision Records. When you're considering a non-obvious tradeoff
(library choice, infra topology, data shape), add a new ADR before or
alongside the code change. Existing ADRs are good examples of the
required brevity and structure.
