output "function_name" {
  description = "Lambda function name."
  value       = aws_lambda_function.function.function_name
}

output "function_arn" {
  description = "Lambda function ARN."
  value       = aws_lambda_function.function.arn
}

output "invoke_arn" {
  description = "Lambda invoke ARN (for API Gateway integrations)."
  value       = aws_lambda_function.function.invoke_arn
}

output "role_arn" {
  description = "ARN of the function's IAM execution role."
  value       = aws_iam_role.function.arn
}

output "log_group_arn" {
  description = "ARN of the CloudWatch log group for this function."
  value       = aws_cloudwatch_log_group.function.arn
}
