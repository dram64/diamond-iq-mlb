###############################################################################
# Terraform remote-state bootstrap
#
# Creates the S3 bucket and DynamoDB lock table that the main stack uses for
# its remote backend. This stack is APPLIED ONCE with local state, because
# the very thing it creates (the S3 bucket) is what the main stack needs to
# exist before its own `terraform init` can run.
#
# After apply, copy the backend_config_hcl output into infrastructure/main.tf.
###############################################################################

terraform {
  required_version = ">= 1.7"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "diamond-iq"
      ManagedBy   = "terraform"
      Environment = var.environment
      Component   = "tfstate-bootstrap"
    }
  }
}

data "aws_caller_identity" "current" {}

locals {
  account_id  = data.aws_caller_identity.current.account_id
  bucket_name = "diamond-iq-tfstate-${local.account_id}"
  lock_table  = "diamond-iq-tfstate-locks"
}

###############################################################################
# State bucket
###############################################################################

resource "aws_s3_bucket" "tfstate" {
  bucket = local.bucket_name

  # Safety: prevent accidental deletion of the state bucket via Terraform.
  # Manually delete with `aws s3 rb` only after destroying the main stack.
  force_destroy = false
}

resource "aws_s3_bucket_versioning" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Deny any non-TLS access. Belt-and-suspenders alongside the public-access
# block — defends against misconfigured client SDKs that might fall back to
# plain HTTP.
data "aws_iam_policy_document" "tfstate_tls_only" {
  statement {
    sid     = "DenyNonTLS"
    effect  = "Deny"
    actions = ["s3:*"]

    resources = [
      aws_s3_bucket.tfstate.arn,
      "${aws_s3_bucket.tfstate.arn}/*",
    ]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "tfstate_tls_only" {
  bucket = aws_s3_bucket.tfstate.id
  policy = data.aws_iam_policy_document.tfstate_tls_only.json

  # Public-access-block must finalize first so AWS doesn't reject the policy
  # as one that "could grant public access".
  depends_on = [aws_s3_bucket_public_access_block.tfstate]
}

###############################################################################
# State lock table
###############################################################################

resource "aws_dynamodb_table" "tfstate_locks" {
  name         = local.lock_table
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }
}
