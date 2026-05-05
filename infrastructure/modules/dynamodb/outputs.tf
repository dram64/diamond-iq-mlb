output "table_name" {
  description = "Name of the games table."
  value       = aws_dynamodb_table.games.name
}

output "table_arn" {
  description = "ARN of the games table."
  value       = aws_dynamodb_table.games.arn
}

output "stream_arn" {
  description = "ARN of the DynamoDB stream feeding the real-time WebSocket pipeline."
  value       = aws_dynamodb_table.games.stream_arn
}
