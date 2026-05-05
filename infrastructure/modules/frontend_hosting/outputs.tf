output "bucket_name" {
  description = "S3 origin bucket — used by the GitHub Actions deploy workflow as the s3 sync target."
  value       = aws_s3_bucket.frontend.id
}

output "bucket_arn" {
  description = "S3 origin bucket ARN — used by the OIDC role to scope frontend deploy permissions."
  value       = aws_s3_bucket.frontend.arn
}

output "distribution_id" {
  description = "CloudFront distribution id — used by the GitHub Actions deploy workflow to invalidate cache."
  value       = aws_cloudfront_distribution.frontend.id
}

output "distribution_arn" {
  description = "CloudFront distribution ARN — used by the OIDC role to scope cache-invalidation permissions."
  value       = aws_cloudfront_distribution.frontend.arn
}

output "distribution_domain_name" {
  description = "CloudFront distribution domain (e.g. d12345.cloudfront.net) — DNS target for the Cloudflare CNAME."
  value       = aws_cloudfront_distribution.frontend.domain_name
}

output "acm_certificate_arn" {
  description = "ACM certificate ARN."
  value       = aws_acm_certificate.frontend.arn
}

output "acm_validation_records" {
  description = "DNS validation records emitted by ACM. Surface these as Checkpoint #1 — must be added in Cloudflare with the orange cloud DISABLED."
  value = [
    for o in aws_acm_certificate.frontend.domain_validation_options : {
      name  = o.resource_record_name
      type  = o.resource_record_type
      value = o.resource_record_value
    }
  ]
}
