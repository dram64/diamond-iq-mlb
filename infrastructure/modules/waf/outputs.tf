output "web_acl_arn" {
  description = "ARN of the Web ACL — passed to the CloudFront distribution's web_acl_id field."
  value       = aws_wafv2_web_acl.this.arn
}

output "web_acl_id" {
  description = "Internal Web ACL ID (not commonly used; prefer ARN)."
  value       = aws_wafv2_web_acl.this.id
}

output "web_acl_name" {
  description = "Web ACL name. Used in CloudWatch alarm dimensions."
  value       = aws_wafv2_web_acl.this.name
}

output "log_group_name" {
  description = "CloudWatch log group capturing WAF requests."
  value       = aws_cloudwatch_log_group.waf.name
}

output "metric_name" {
  description = "Top-level metric name for the Web ACL — used by alarms (Region-scoped resource → CloudFront global)."
  value       = "${var.name_prefix}-waf"
}
