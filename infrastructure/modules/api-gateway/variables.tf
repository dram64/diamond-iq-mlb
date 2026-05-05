variable "api_name" {
  description = "Name of the API Gateway HTTP API."
  type        = string
}

variable "api_lambda_name" {
  description = "Name of the Lambda function backing the API."
  type        = string
}

variable "api_lambda_invoke_arn" {
  description = "Invoke ARN of the API Lambda."
  type        = string
}

variable "cors_allow_origins" {
  description = "Allowed CORS origins for the HTTP API."
  type        = list(string)
}

variable "log_retention_days" {
  description = "CloudWatch Logs retention for the API access log group."
  type        = number
  default     = 14
}
