# Terraform remote-state bootstrap

One-time stack that creates the S3 bucket and DynamoDB lock table the main
infrastructure stack uses for its remote backend.

## Why this exists

Terraform needs the S3 bucket configured in its backend block to exist
**before** `terraform init` will succeed. The chicken-and-egg solution is to
manage the bucket itself with a separate stack that uses **local** state.
That's this directory.

After the bootstrap is applied, the main stack (`infrastructure/`) uses the
S3 bucket created here as its remote backend. The bootstrap is essentially
done — you should never need to apply it again unless you're recovering from
state loss.

## What it creates

| Resource | Name | Purpose |
| --- | --- | --- |
| `aws_s3_bucket` | `diamond-iq-tfstate-<account-id>` | Holds remote `terraform.tfstate` for the main stack |
| `aws_s3_bucket_versioning` | (on bucket above) | Enables versioning so you can roll state back |
| `aws_s3_bucket_server_side_encryption_configuration` | (on bucket above) | AES-256 server-side encryption at rest |
| `aws_s3_bucket_public_access_block` | (on bucket above) | All four "block public access" toggles enabled |
| `aws_s3_bucket_policy` | (on bucket above) | Denies any non-TLS request via `aws:SecureTransport` |
| `aws_dynamodb_table` | `diamond-iq-tfstate-locks` | Distributed lock so two `terraform apply`s can't race; PITR on |

`force_destroy = false` on the bucket is intentional. To delete the bucket
later, empty it manually with `aws s3 rb` only after the main stack is
destroyed.

## How to apply (one-time)

From the project root:

```bash
cd infrastructure/bootstrap
terraform init
terraform plan
terraform apply
```

Terraform will prompt for confirmation. Type `yes`.

Outputs:

- `state_bucket_name` — the bucket name
- `lock_table_name` — the lock table name
- `backend_config_hcl` — a ready-to-paste `terraform { backend "s3" { ... } }`
  block to drop into `infrastructure/main.tf` for the main stack

## Local state file

This stack uses local state (`terraform.tfstate` in this directory) on
purpose. It is **gitignored** — see the project root `.gitignore`. The state
itself is recoverable: if you lose the local file, you can `terraform import`
the bucket and lock table back.

If you do lose it:

```bash
cd infrastructure/bootstrap
terraform init
terraform import aws_s3_bucket.tfstate diamond-iq-tfstate-<account-id>
terraform import aws_dynamodb_table.tfstate_locks diamond-iq-tfstate-locks
# ...and the rest of the resources, in dependency order
```

## How to destroy (rare)

Only run this **after** the main stack has been destroyed. Otherwise the
main stack's remote state file lives inside the bucket you're about to
delete.

```bash
cd infrastructure/bootstrap

# 1. Empty the bucket (versioning is on, so all versions must go)
aws s3api delete-objects --bucket diamond-iq-tfstate-<account-id> \
  --delete "$(aws s3api list-object-versions \
    --bucket diamond-iq-tfstate-<account-id> \
    --query='{Objects: Versions[].{Key:Key, VersionId:VersionId}}')"

# 2. Then let Terraform tear the rest down
terraform destroy
```
