###############################################################################
# CloudFront distribution fronting the API Gateway HTTP API.
#
# AWS WAFv2 cannot attach directly to API Gateway HTTP APIs (v2). CloudFront
# is the standard pattern that unlocks WAF for HTTP API origins. The
# distribution uses managed origin/cache policies (no caching of API
# responses; forward all viewer headers except Host).
#
# The CloudFront distribution domain (something.cloudfront.net) is the new
# public entry point — frontend points here, the API Gateway URL stays as a
# documented bypass for ops debugging.
###############################################################################

locals {
  # API Gateway returns "https://abcd1234.execute-api.us-east-1.amazonaws.com".
  # CloudFront origin domain wants just the host portion.
  api_origin_domain = replace(replace(module.api_gateway.api_endpoint, "https://", ""), "http://", "")
  api_origin_id     = "${local.name_prefix}-api"

  # AWS-managed CloudFront policies (stable IDs).
  # https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/using-managed-cache-policies.html
  cf_managed_cache_policy_caching_disabled = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"

  # https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/using-managed-origin-request-policies.html
  # AllViewerExceptHostHeader — forwards every viewer header to the origin
  # except Host. API Gateway requires its own Host header to route correctly,
  # so dropping the viewer's Host (which would be the CloudFront domain) is
  # mandatory for HTTP API origins.
  cf_managed_origin_request_policy_all_viewer_except_host = "b689b0a8-53d0-40ab-baf2-68738e2966ac"
}

resource "aws_cloudfront_distribution" "api" {
  enabled             = true
  comment             = "${local.name_prefix} — fronts API Gateway HTTP API for WAF coverage"
  is_ipv6_enabled     = true
  http_version        = "http2and3"
  price_class         = "PriceClass_100" # NA + EU; cheapest tier, fine for portfolio
  retain_on_delete    = false
  wait_for_deployment = false

  # WAF attachment.
  web_acl_id = module.waf.web_acl_arn

  origin {
    domain_name = local.api_origin_domain
    origin_id   = local.api_origin_id

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  default_cache_behavior {
    target_origin_id       = local.api_origin_id
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true

    cache_policy_id          = local.cf_managed_cache_policy_caching_disabled
    origin_request_policy_id = local.cf_managed_origin_request_policy_all_viewer_except_host
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
      # Geo blocking lives in WAF (with COUNT-mode opt-in), not here. CloudFront
      # geo_restriction is a blunter tool (returns 403 with no logging context).
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}
