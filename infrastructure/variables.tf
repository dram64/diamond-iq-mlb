variable "aws_region" {
  description = "AWS region to deploy into."
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Deployment environment tag."
  type        = string
  default     = "prod"
}

variable "github_repo" {
  description = "GitHub repository (owner/name) trusted by the OIDC deploy role."
  type        = string
  default     = "dram64/diamond-iq"
}

variable "frontend_origin" {
  description = "Allowed CORS origin for the HTTP API. Kept for backwards compatibility with existing callers; cors_allow_origins is the actual list passed to API Gateway."
  type        = string
  default     = "http://localhost:5173"
}

# ── Phase 5J — Frontend hosting ────────────────────────────────────────────

variable "frontend_domain_name" {
  description = "FQDN the public frontend SPA is served from (Phase 5J). Cloudflare-managed; DNS records added manually outside Terraform."
  type        = string
  default     = "diamond-iq.dram-soc.org"
}

variable "frontend_bucket_name" {
  description = "Globally-unique S3 bucket name for the frontend SPA origin (Phase 5J)."
  type        = string
  default     = "diamond-iq-frontend"
}

variable "cors_allow_origins" {
  description = "Full CORS allow-list for the HTTP API. Includes the production frontend origin (Phase 5J) plus localhost ports 5173-5176 for dev. Frontends served from any other origin will be CORS-rejected by API Gateway."
  type        = list(string)
  default = [
    "https://diamond-iq.dram-soc.org",
    "http://localhost:5173",
    "http://localhost:5174",
    "http://localhost:5175",
    "http://localhost:5176",
  ]
}

variable "alert_email" {
  description = "Email address subscribed to operational alerts (SNS). Supplied via terraform.tfvars (gitignored) or TF_VAR_alert_email; intentionally has no default so a missing value fails the plan loudly."
  type        = string
  # No default — must be set externally so secrets/PII never land in source.

  # Reject empty/whitespace/malformed values at plan time. Without this, a
  # misconfigured GitHub secret would silently trigger a destroy/recreate of
  # the email subscription, breaking the alert path until someone manually
  # restores it. We've already been bitten by this once.
  validation {
    condition     = can(regex("^\\S+@\\S+\\.\\S+$", var.alert_email))
    error_message = "alert_email must be a non-empty, well-formed email address (e.g. set TF_VAR_alert_email or terraform.tfvars)."
  }
}

# ── WAF (Security Layer Phase 1) ────────────────────────────────────────────

variable "managed_rule_actions" {
  description = "Override action for each managed WAF rule group: count (observation) or block (enforcement)."
  type        = map(string)
  default = {
    common_rule_set    = "count"
    known_bad_inputs   = "count"
    ip_reputation_list = "count"
    bot_control        = "count"
  }
}

variable "rate_limit_default" {
  description = "Per-IP request limit per 5-min window for the default WAF rate-limit rule (excludes the welcome route)."
  type        = number
  default     = 2000
}

variable "rate_limit_sensitive" {
  description = "Per-IP request limit per 5-min window for /content/today and /scoreboard/today."
  type        = number
  default     = 300
}

variable "enable_geo_blocking" {
  description = "Flip the geo rule from COUNT to BLOCK for blocked_countries."
  type        = bool
  default     = false
}

variable "blocked_countries" {
  description = "ISO 3166-1 alpha-2 country codes evaluated by the WAF geo rule."
  type        = list(string)
  default     = ["CN", "RU", "KP", "IR"]
}

variable "blocked_user_agents" {
  description = "Substrings (case-insensitive) matched against User-Agent to block known scanners and exploit tooling."
  type        = list(string)
  default = [
    "sqlmap",
    "nikto",
    "nmap",
    "masscan",
    "dirbuster",
    "gobuster",
    "wpscan",
    "nuclei",
    "acunetix",
  ]
}

variable "dev_allow_list_cidrs" {
  description = "CIDRs allowed past every other WAF rule. Supplied via terraform.tfvars (gitignored) or TF_VAR_dev_allow_list_cidrs; defaults to empty so production never has an inadvertent allow-list."
  type        = list(string)
  default     = []
}
