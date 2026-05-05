output "deploy_role_arn" {
  description = "ARN of the GitHub Actions deploy IAM role."
  value       = aws_iam_role.deploy.arn
}

output "deploy_role_name" {
  description = "Name of the GitHub Actions deploy IAM role."
  value       = aws_iam_role.deploy.name
}

output "openid_connect_provider_arn" {
  description = "ARN of the GitHub Actions OIDC provider."
  value       = aws_iam_openid_connect_provider.github.arn
}
