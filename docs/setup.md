# Setup

End-to-end first-time setup for Diamond IQ.

## Prerequisites

| Tool | Version | Notes |
| --- | --- | --- |
| Python | 3.12 | Lambda runtime version; pinned via `.python-version` |
| [uv](https://docs.astral.sh/uv/) | 0.10+ | Manages Python venv + lockfile |
| Terraform | 1.7+ | `winget install Hashicorp.Terraform` on Windows |
| Git | any modern | |
| AWS CLI | v2 | For credential setup and verification |
| AWS account | | With IAM user permissions to apply the stack |
| Node.js | 24 LTS | Frontend only |

Verify each:

```bash
python --version          # 3.12.x
uv --version              # 0.10.x or later
terraform -version        # v1.7 or later
aws --version             # 2.x
git --version             # any modern
```

## 1. Clone

```bash
git clone https://github.com/dram64/diamond-iq.git
cd diamond-iq
```

## 2. Configure AWS credentials

Create an IAM user with sufficient permissions to apply the bootstrap
and main stacks (or use an existing admin profile). Then:

```bash
aws configure --profile diamond-iq
# Access key ID:     <paste>
# Secret access key: <paste>
# Region:            us-east-1
# Output format:     json

aws sts get-caller-identity --profile diamond-iq
# Should print your IAM user ARN, NOT the root user.

export AWS_PROFILE=diamond-iq           # bash / zsh
$env:AWS_PROFILE = "diamond-iq"         # PowerShell
```

> **Never paste credentials into chat, IDE selections, or git history.**
> Run `aws configure` yourself locally; share only the
> `aws sts get-caller-identity` output (which is non-sensitive).

## 3. Set up a billing alarm

In the AWS console: **Billing → Alarms → Create**. Create a
CloudWatch billing alarm at a threshold you're comfortable with
(I use **$10**) on `EstimatedCharges` in `us-east-1`. Note that
billing metrics live in `us-east-1` only regardless of where your
resources actually are.

## 4. Bootstrap Terraform state

Creates the S3 bucket + DynamoDB lock table the main stack uses for
remote state. One-time:

```bash
cd infrastructure/bootstrap
terraform init
terraform plan
terraform apply
# Type `yes` to confirm
```

Or use the helper:

```bash
scripts/bootstrap_tf.sh
```

Detailed walkthrough: [infrastructure/bootstrap/README.md](../infrastructure/bootstrap/README.md).

## 5. Apply the main stack

```bash
cd ../             # back to infrastructure/
terraform init
terraform plan
terraform apply
```

26 resources created. Outputs the API endpoint URL and the GitHub
deploy role ARN (used by Phase 7 CI/CD).

## 6. Verify deployment

```bash
# DynamoDB table
aws dynamodb describe-table --table-name diamond-iq-games \
  --query "Table.{Name:TableName,Status:TableStatus,Mode:BillingModeSummary.BillingMode}"

# Lambdas
aws lambda list-functions \
  --query "Functions[?starts_with(FunctionName, 'diamond-iq')].{Name:FunctionName,Runtime:Runtime}"

# API Gateway
aws apigatewayv2 get-apis \
  --query "Items[?Name=='diamond-iq-api'].{ApiId:ApiId,Endpoint:ApiEndpoint}"

# Wait 60-90s for the first ingest to fire, then:
aws dynamodb scan --table-name diamond-iq-games --select COUNT

# Hit the live API:
curl https://<api-id>.execute-api.us-east-1.amazonaws.com/scoreboard/today
```

## 7. Run tests locally

```bash
uv sync                   # creates .venv, installs deps from uv.lock
uv run pytest             # 53 tests
uv run ruff check .       # lint
uv run black --check .    # format
```

## 8. Run Lambdas locally against real MLB API

The `scripts/` folder has CLI wrappers that exercise the Lambda
handlers without deploying:

```bash
# Ingest, dry-run (moto-mocked DynamoDB; hits real MLB API)
uv run python scripts/invoke_ingest_locally.py --dry-run

# Ingest, real DynamoDB (requires the stack to be deployed)
uv run python scripts/invoke_ingest_locally.py --table-name diamond-iq-games

# API, scoreboard route, seeded from the captured fixture
uv run python scripts/invoke_api_locally.py --route scoreboard --seed fixture

# API, single game, seeded from a live MLB pull
uv run python scripts/invoke_api_locally.py \
  --route game --game-id 822909 --date 2026-04-25 --seed live
```

## 9. Optional: install pre-commit hooks

```bash
uv tool install pre-commit
pre-commit install
pre-commit run --all-files
```

This runs ruff, black, terraform fmt, trailing-whitespace, and
end-of-file-fixer before every commit.

## Common gotchas

### Git Bash mangles AWS CLI log group paths
On Windows Git Bash, paths starting with `/` (e.g. `/aws/lambda/...`)
get rewritten to `C:/Program Files/Git/aws/lambda/...`. Workaround:

```bash
export MSYS_NO_PATHCONV=1
aws logs tail /aws/lambda/diamond-iq-ingest-live-games --since 5m
```

Or run from PowerShell, where the path-conversion problem doesn't
exist.

### UTC date vs local date for "today's games"
The ingest Lambda runs in UTC. MLB groups games by local date. A late
West Coast start (gameDate `2026-04-25T03:10:00Z`) is keyed under
DynamoDB partition `GAME#2026-04-25`, not `GAME#2026-04-24`, even
though it's "tonight's game" in Pacific time. The ingest queries both
yesterday and today UTC every minute to cover this. The frontend
should query both dates around UTC midnight if it wants to render a
user's local-day view. See [ADR 004](adr/004-two-date-ingestion-window.md).

### IAM billing access requires the root account to enable it
By default IAM users (even admins) cannot view the Billing console.
Sign in as root once, go to **Account → IAM user and role access to
Billing information**, and tick **Activate**. This is the official
AWS guidance and it's a one-time toggle.

### Terraform pre-commit hook needs `terraform` on PATH
The `terraform_fmt` pre-commit hook spawns its own subshell that
doesn't inherit `winget`'s recent PATH additions. After installing
Terraform, restart your terminal, or set `PCT_TFPATH` to the
executable path before commits that involve `.tf` files.

### GitHub Actions API rate limit when polling
Anonymous GitHub API calls are limited to 60/hour per IP. If you're
polling workflow status from scripts, authenticate with a PAT or use
`gh` CLI.
