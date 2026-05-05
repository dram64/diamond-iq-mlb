variable "name_prefix" {
  description = "Project name prefix used in resource names (e.g., diamond-iq)."
  type        = string
}

variable "scope" {
  description = "WAFv2 scope. Use CLOUDFRONT for CloudFront distributions, REGIONAL for ALB/API-Gateway-REST."
  type        = string
  default     = "CLOUDFRONT"
  validation {
    condition     = contains(["CLOUDFRONT", "REGIONAL"], var.scope)
    error_message = "scope must be CLOUDFRONT or REGIONAL."
  }
}

variable "managed_rule_actions" {
  description = "Override action for each managed rule group (count for observation, block to enforce)."
  type        = map(string)
  default = {
    common_rule_set    = "count"
    known_bad_inputs   = "count"
    ip_reputation_list = "count"
    bot_control        = "count"
  }
  validation {
    condition     = alltrue([for v in values(var.managed_rule_actions) : contains(["count", "block"], v)])
    error_message = "managed_rule_actions values must be count or block."
  }
}

variable "rate_limit_default" {
  description = "Per-IP request limit over a 5-minute window for the default rate-limit rule. WAF requires >= 100."
  type        = number
  default     = 2000
  validation {
    condition     = var.rate_limit_default >= 100
    error_message = "WAF rate-based rules require a limit of at least 100."
  }
}

variable "rate_limit_sensitive" {
  description = "Per-IP request limit over a 5-minute window for /content/today and /scoreboard/today."
  type        = number
  default     = 300
  validation {
    condition     = var.rate_limit_sensitive >= 100
    error_message = "WAF rate-based rules require a limit of at least 100."
  }
}

variable "enable_geo_blocking" {
  description = "If true, geo rule BLOCKs requests from blocked_countries. If false, the rule runs in COUNT for visibility only."
  type        = bool
  default     = false
}

variable "blocked_countries" {
  description = "ISO 3166-1 alpha-2 country codes evaluated by the geo rule."
  type        = list(string)
  default     = ["CN", "RU", "KP", "IR"]
}

variable "blocked_user_agents" {
  description = "Substrings (case-insensitive) matched against the User-Agent header to block known scanners and exploit tooling."
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
  description = "CIDRs explicitly allowed past every other rule (for development/admin debugging). Empty = no dev allow rule."
  type        = list(string)
  default     = []
}

variable "log_retention_days" {
  description = "Retention for the WAF CloudWatch log group."
  type        = number
  default     = 14
}
