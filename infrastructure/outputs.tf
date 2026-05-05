output "api_endpoint" {
  description = "Public base URL for the HTTP API."
  value       = module.api_gateway.api_endpoint
}

output "games_table_name" {
  description = "Name of the games DynamoDB table."
  value       = module.dynamodb.table_name
}

output "games_stream_arn" {
  description = "ARN of the games table DynamoDB stream (consumed by the stream-processor Lambda)."
  value       = module.dynamodb.stream_arn
}

output "connections_table_name" {
  description = "Name of the WebSocket connections DynamoDB table."
  value       = aws_dynamodb_table.connections.name
}

output "websocket_url" {
  description = "Public WebSocket entry point. Frontend points VITE_WS_URL here."
  value       = "${aws_apigatewayv2_api.ws.api_endpoint}/${aws_apigatewayv2_stage.ws.name}"
}

output "websocket_api_id" {
  description = "WebSocket API ID — used by the stream processor to construct the management API endpoint."
  value       = aws_apigatewayv2_api.ws.id
}

output "ingest_lambda_name" {
  description = "Name of the ingest Lambda function."
  value       = module.lambda_ingest.function_name
}

output "api_lambda_name" {
  description = "Name of the API Lambda function."
  value       = module.lambda_api.function_name
}

output "github_deploy_role_arn" {
  description = "ARN of the GitHub Actions OIDC deploy role."
  value       = module.oidc.deploy_role_arn
}

output "ingest_schedule_rule_name" {
  description = "Name of the EventBridge rule that fires the ingest Lambda."
  value       = module.events.rule_name
}

output "cloudfront_url" {
  description = "Public CloudFront entry point fronting the API. Set frontend VITE_API_URL to this; the api_endpoint output is preserved as a documented bypass for ops debugging."
  value       = "https://${aws_cloudfront_distribution.api.domain_name}"
}

output "waf_web_acl_arn" {
  description = "ARN of the WAF Web ACL attached to the CloudFront distribution."
  value       = module.waf.web_acl_arn
}

output "waf_log_group_name" {
  description = "CloudWatch log group capturing WAF requests."
  value       = module.waf.log_group_name
}

# ── Phase 5J — frontend hosting ────────────────────────────────────────────

output "frontend_bucket_name" {
  description = "S3 bucket the frontend SPA is uploaded to. Used by the GitHub Actions deploy workflow."
  value       = module.frontend_hosting.bucket_name
}

output "frontend_distribution_id" {
  description = "CloudFront distribution id for the SPA. Used by the deploy workflow to invalidate cache."
  value       = module.frontend_hosting.distribution_id
}

output "frontend_distribution_domain_name" {
  description = "CloudFront distribution domain (e.g. d12345.cloudfront.net). Surface as Checkpoint #2 — the final Cloudflare CNAME target."
  value       = module.frontend_hosting.distribution_domain_name
}

output "frontend_acm_validation_records" {
  description = "ACM validation CNAME(s). Surface as Checkpoint #1 — must be added in Cloudflare with the orange cloud DISABLED (proxied DNS breaks ACM validation)."
  value       = module.frontend_hosting.acm_validation_records
}

output "frontend_url" {
  description = "Public URL the React SPA is served from after Cloudflare DNS is wired."
  value       = "https://${var.frontend_domain_name}"
}
