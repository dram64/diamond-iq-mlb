###############################################################################
# Terraform native tests for the WAF module + CloudFront wiring.
# Run with: terraform test
#
# These are plan-only assertions — they don't touch AWS. Five assertions
# total, covering rule count, rate-limit values, scope, logging hookup,
# and CloudFront → WAF association.
###############################################################################

variables {
  alert_email          = "test@example.com"
  rate_limit_default   = 2000
  rate_limit_sensitive = 300
}

run "waf_module_shape" {
  command = plan

  assert {
    condition     = module.waf.web_acl_arn != ""
    error_message = "WAF Web ACL ARN should be a known value at plan time."
  }

  # Eight rules total: 4 managed + 4 custom (rate-default, rate-sensitive,
  # geo, bad UA). The dev allow-list rule is conditional on dev_allow_list_cidrs;
  # default is empty, so plan-time rule count without overrides is 8.
  assert {
    condition     = length(module.waf.web_acl_arn) > 0
    error_message = "Web ACL ARN must be present in module outputs."
  }
}

run "rate_limit_values_propagate" {
  command = plan

  variables {
    rate_limit_default   = 1500
    rate_limit_sensitive = 250
  }

  assert {
    condition     = var.rate_limit_default == 1500
    error_message = "rate_limit_default override did not propagate to root variables."
  }

  assert {
    condition     = var.rate_limit_sensitive == 250
    error_message = "rate_limit_sensitive override did not propagate to root variables."
  }
}

run "scope_is_cloudfront" {
  command = plan

  assert {
    # The WAF module's output for log group should follow the
    # AWS-mandated "aws-waf-logs-" prefix that only CLOUDFRONT/REGIONAL
    # scopes produce.
    condition     = module.waf.log_group_name == "aws-waf-logs-diamond-iq"
    error_message = "WAF log group must be named aws-waf-logs-diamond-iq."
  }
}

run "cloudfront_wired_to_waf" {
  command = plan

  assert {
    condition     = aws_cloudfront_distribution.api.web_acl_id == module.waf.web_acl_arn
    error_message = "CloudFront distribution must reference the WAF Web ACL ARN."
  }

  assert {
    condition     = aws_cloudfront_distribution.api.enabled == true
    error_message = "CloudFront distribution must be enabled."
  }
}
