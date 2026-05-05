variable "aws_region" {
  description = "AWS region for the state bucket and lock table."
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Deployment environment tag applied to bootstrap resources."
  type        = string
  default     = "prod"
}
