variable "rule_name" {
  description = "EventBridge rule name."
  type        = string
}

variable "ingest_lambda_name" {
  description = "Name of the ingest Lambda function."
  type        = string
}

variable "ingest_lambda_arn" {
  description = "ARN of the ingest Lambda function."
  type        = string
}
