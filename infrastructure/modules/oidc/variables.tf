variable "github_repo" {
  description = "GitHub repository (owner/name) authorized to assume the deploy role."
  type        = string
}

variable "role_name" {
  description = "Name of the GitHub Actions deploy IAM role."
  type        = string
}

variable "name_prefix" {
  description = "Project name prefix used for ARN scoping."
  type        = string
}

variable "account_id" {
  description = "AWS account id (for IAM ARN construction)."
  type        = string
}

variable "aws_region" {
  description = "AWS region (for ARN construction)."
  type        = string
}

variable "state_bucket_name" {
  description = "Name of the Terraform state bucket the deploy role can access."
  type        = string
}

variable "lock_table_name" {
  description = "Name of the Terraform lock table the deploy role can access."
  type        = string
}
