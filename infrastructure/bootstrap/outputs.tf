output "state_bucket_name" {
  description = "Name of the S3 bucket that stores Terraform state for the main stack."
  value       = aws_s3_bucket.tfstate.id
}

output "lock_table_name" {
  description = "Name of the DynamoDB table that holds Terraform state locks."
  value       = aws_dynamodb_table.tfstate_locks.id
}

output "aws_region" {
  description = "Region the state bucket and lock table live in."
  value       = var.aws_region
}

# Copy the value of this output into infrastructure/main.tf as the
# `terraform { backend "s3" { ... } }` block when wiring up the main stack.
output "backend_config_hcl" {
  description = "Backend configuration block to paste into the main stack."
  value       = <<-EOT
    terraform {
      backend "s3" {
        bucket         = "${aws_s3_bucket.tfstate.id}"
        key            = "main/terraform.tfstate"
        region         = "${var.aws_region}"
        dynamodb_table = "${aws_dynamodb_table.tfstate_locks.id}"
        encrypt        = true
      }
    }
  EOT
}
