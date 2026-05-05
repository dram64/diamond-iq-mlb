###############################################################################
# AWS WAFv2 Web ACL.
#
# Rule order (lower priority = evaluated first):
#   0   dev_allow_list           Allow CIDRs in var.dev_allow_list_cidrs
#  10   ip_reputation            AWS managed; Amazon IP reputation list
#  20   common_rule_set          AWS managed; OWASP-style baseline
#  30   known_bad_inputs         AWS managed; exploit signatures
#  40   bot_control              AWS managed; bot detection
#  50   blocked_user_agents      Custom; Block known-bad UAs
#  60   geo_block                Custom; Block (or Count) blocked_countries
#  70   rate_limit_sensitive     Custom; Rate-limit /content + /scoreboard
#  80   rate_limit_default       Custom; Rate-limit everything except "/"
#
# Default action is Allow — every block decision is explicit, every Allow is
# logged with the rule that matched. Default-deny would lock out legitimate
# traffic during the COUNT-mode observation period.
###############################################################################

resource "aws_wafv2_ip_set" "dev_allow" {
  count              = length(var.dev_allow_list_cidrs) > 0 ? 1 : 0
  name               = "${var.name_prefix}-dev-allow"
  description        = "CIDRs allowed past every other WAF rule for dev or admin debugging."
  scope              = var.scope
  ip_address_version = "IPV4"
  addresses          = var.dev_allow_list_cidrs
}

resource "aws_wafv2_web_acl" "this" {
  name        = "${var.name_prefix}-waf"
  description = "Diamond IQ Web ACL. Default action Allow. Specific rules block."
  scope       = var.scope

  default_action {
    allow {}
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "${var.name_prefix}-waf"
    sampled_requests_enabled   = true
  }

  ###########################################################################
  # 0 — Dev allow-list (only when CIDRs are supplied)
  ###########################################################################
  dynamic "rule" {
    for_each = length(var.dev_allow_list_cidrs) > 0 ? [1] : []
    content {
      name     = "dev-allow-list"
      priority = 0
      action {
        allow {}
      }
      statement {
        ip_set_reference_statement {
          arn = aws_wafv2_ip_set.dev_allow[0].arn
        }
      }
      visibility_config {
        cloudwatch_metrics_enabled = true
        metric_name                = "${var.name_prefix}-dev-allow"
        sampled_requests_enabled   = true
      }
    }
  }

  ###########################################################################
  # 10 — AWS managed: Amazon IP reputation list
  ###########################################################################
  rule {
    name     = "aws-managed-ip-reputation"
    priority = 10

    dynamic "override_action" {
      for_each = var.managed_rule_actions["ip_reputation_list"] == "count" ? [1] : []
      content {
        count {}
      }
    }
    dynamic "override_action" {
      for_each = var.managed_rule_actions["ip_reputation_list"] == "block" ? [1] : []
      content {
        none {}
      }
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesAmazonIpReputationList"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.name_prefix}-ip-reputation"
      sampled_requests_enabled   = true
    }
  }

  ###########################################################################
  # 20 — AWS managed: Common Rule Set (OWASP-ish)
  ###########################################################################
  rule {
    name     = "aws-managed-common"
    priority = 20

    dynamic "override_action" {
      for_each = var.managed_rule_actions["common_rule_set"] == "count" ? [1] : []
      content {
        count {}
      }
    }
    dynamic "override_action" {
      for_each = var.managed_rule_actions["common_rule_set"] == "block" ? [1] : []
      content {
        none {}
      }
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesCommonRuleSet"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.name_prefix}-common"
      sampled_requests_enabled   = true
    }
  }

  ###########################################################################
  # 30 — AWS managed: Known Bad Inputs
  ###########################################################################
  rule {
    name     = "aws-managed-known-bad-inputs"
    priority = 30

    dynamic "override_action" {
      for_each = var.managed_rule_actions["known_bad_inputs"] == "count" ? [1] : []
      content {
        count {}
      }
    }
    dynamic "override_action" {
      for_each = var.managed_rule_actions["known_bad_inputs"] == "block" ? [1] : []
      content {
        none {}
      }
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesKnownBadInputsRuleSet"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.name_prefix}-known-bad-inputs"
      sampled_requests_enabled   = true
    }
  }

  ###########################################################################
  # 40 — AWS managed: Bot Control (basic tier)
  ###########################################################################
  rule {
    name     = "aws-managed-bot-control"
    priority = 40

    dynamic "override_action" {
      for_each = var.managed_rule_actions["bot_control"] == "count" ? [1] : []
      content {
        count {}
      }
    }
    dynamic "override_action" {
      for_each = var.managed_rule_actions["bot_control"] == "block" ? [1] : []
      content {
        none {}
      }
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesBotControlRuleSet"
        vendor_name = "AWS"
        managed_rule_group_configs {
          aws_managed_rules_bot_control_rule_set {
            inspection_level = "COMMON"
          }
        }
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.name_prefix}-bot-control"
      sampled_requests_enabled   = true
    }
  }

  ###########################################################################
  # 50 — Custom: Block known-bad User-Agent substrings
  ###########################################################################
  rule {
    name     = "block-known-bad-user-agents"
    priority = 50
    action {
      block {}
    }

    statement {
      or_statement {
        dynamic "statement" {
          for_each = var.blocked_user_agents
          content {
            byte_match_statement {
              search_string         = statement.value
              positional_constraint = "CONTAINS"
              field_to_match {
                single_header {
                  name = "user-agent"
                }
              }
              text_transformation {
                priority = 0
                type     = "LOWERCASE"
              }
            }
          }
        }
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.name_prefix}-bad-user-agents"
      sampled_requests_enabled   = true
    }
  }

  ###########################################################################
  # 60 — Custom: Geo blocking (Count when disabled, Block when enabled)
  ###########################################################################
  rule {
    name     = "geo-block"
    priority = 60

    dynamic "action" {
      for_each = var.enable_geo_blocking ? [1] : []
      content {
        block {}
      }
    }
    dynamic "action" {
      for_each = var.enable_geo_blocking ? [] : [1]
      content {
        count {}
      }
    }

    statement {
      geo_match_statement {
        country_codes = var.blocked_countries
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.name_prefix}-geo-block"
      sampled_requests_enabled   = true
    }
  }

  ###########################################################################
  # 70 — Custom: Rate-limit sensitive paths (/content, /scoreboard)
  ###########################################################################
  rule {
    name     = "rate-limit-sensitive-paths"
    priority = 70
    action {
      block {
        custom_response {
          response_code = 429
        }
      }
    }

    statement {
      rate_based_statement {
        limit                 = var.rate_limit_sensitive
        aggregate_key_type    = "IP"
        evaluation_window_sec = 300

        scope_down_statement {
          or_statement {
            statement {
              byte_match_statement {
                search_string         = "/content/today"
                positional_constraint = "STARTS_WITH"
                field_to_match {
                  uri_path {}
                }
                text_transformation {
                  priority = 0
                  type     = "NONE"
                }
              }
            }
            statement {
              byte_match_statement {
                search_string         = "/scoreboard/today"
                positional_constraint = "STARTS_WITH"
                field_to_match {
                  uri_path {}
                }
                text_transformation {
                  priority = 0
                  type     = "NONE"
                }
              }
            }
          }
        }
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.name_prefix}-rate-sensitive"
      sampled_requests_enabled   = true
    }
  }

  ###########################################################################
  # 80 — Custom: Default rate limit (everything except "/")
  ###########################################################################
  rule {
    name     = "rate-limit-default"
    priority = 80
    action {
      block {
        custom_response {
          response_code = 429
        }
      }
    }

    statement {
      rate_based_statement {
        limit                 = var.rate_limit_default
        aggregate_key_type    = "IP"
        evaluation_window_sec = 300

        scope_down_statement {
          not_statement {
            statement {
              byte_match_statement {
                search_string         = "/"
                positional_constraint = "EXACTLY"
                field_to_match {
                  uri_path {}
                }
                text_transformation {
                  priority = 0
                  type     = "NONE"
                }
              }
            }
          }
        }
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.name_prefix}-rate-default"
      sampled_requests_enabled   = true
    }
  }
}

###############################################################################
# Logging — CloudWatch Logs.
#
# WAFv2 requires the log group name to start with "aws-waf-logs-". This is an
# AWS validation, not Terraform's; the resource will fail to create otherwise.
###############################################################################

resource "aws_cloudwatch_log_group" "waf" {
  name              = "aws-waf-logs-${var.name_prefix}"
  retention_in_days = var.log_retention_days
}

resource "aws_wafv2_web_acl_logging_configuration" "this" {
  log_destination_configs = [aws_cloudwatch_log_group.waf.arn]
  resource_arn            = aws_wafv2_web_acl.this.arn
}
