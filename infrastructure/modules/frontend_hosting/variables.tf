variable "name_prefix" {
  description = "Project name prefix used for naming the bucket, distribution comment, etc."
  type        = string
}

variable "domain_name" {
  description = "FQDN the frontend is served from (e.g. diamond-iq.dram-soc.org). Must be a Cloudflare-managed domain — DNS is added manually outside Terraform."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9.-]+\\.[a-z]{2,}$", var.domain_name))
    error_message = "domain_name must be a lowercase FQDN with a TLD."
  }
}

variable "bucket_name" {
  description = "S3 bucket name for the static-site origin. Globally unique."
  type        = string
}

variable "log_retention_days" {
  description = "CloudWatch Logs retention for any future access-log group. Reserved; not currently used (CloudFront standard logs to S3 are out of scope)."
  type        = number
  default     = 14
}

variable "api_origin" {
  description = "Origin of the API distribution that the frontend's JS will call (e.g. https://d17hrttnkrygh8.cloudfront.net). Used to build the Content-Security-Policy connect-src directive."
  type        = string

  validation {
    condition     = can(regex("^https://", var.api_origin))
    error_message = "api_origin must be an https:// URL."
  }
}
