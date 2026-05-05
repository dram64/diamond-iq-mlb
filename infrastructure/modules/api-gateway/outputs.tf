output "api_id" {
  description = "API Gateway HTTP API id."
  value       = aws_apigatewayv2_api.this.id
}

output "api_endpoint" {
  description = "Public base URL for the HTTP API."
  value       = aws_apigatewayv2_api.this.api_endpoint
}

output "execution_arn" {
  description = "API Gateway execution ARN (for IAM scoping)."
  value       = aws_apigatewayv2_api.this.execution_arn
}

output "access_log_group_arn" {
  description = "ARN of the access log group."
  value       = aws_cloudwatch_log_group.access.arn
}
