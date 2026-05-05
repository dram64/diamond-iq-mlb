###############################################################################
# Frontend hosting (Phase 5J).
#
# Stands up a SECOND CloudFront distribution alongside the existing
# API-fronting distribution (which stays as-is). This one serves the React
# SPA from a private S3 bucket via Origin Access Control (OAC), with:
#
#   - ACM TLS cert for the project's custom domain
#   - SPA fallback rewrites (403/404 → /index.html @ HTTP 200) for client-
#     side routing
#   - Strict security headers (CSP, HSTS, X-Frame-Options, …) via a
#     CloudFront response-headers policy
#   - PriceClass_100 (US/EU/IL) — sufficient for a portfolio audience
#
# What's NOT here, by design:
#   - AWS WAF. Cloudflare's free WAF/DDoS at the orange-cloud proxy layer
#     fronts this distribution. AWS WAF would add ~$5.40/mo for inferior
#     L3/4 coverage. See ADR 014.
#   - The API distribution. d17hrttnkrygh8.cloudfront.net keeps serving
#     the API; this module is a sibling, not a replacement.
###############################################################################

terraform {
  required_providers {
    aws = {
      source                = "hashicorp/aws"
      version               = "~> 5.0"
      configuration_aliases = []
    }
  }
}

###############################################################################
# ACM cert (must be us-east-1 for CloudFront)
#
# DNS validation: ACM emits a CNAME record that must be created manually in
# Cloudflare with the orange cloud DISABLED (proxied DNS breaks the ACM
# validation handshake). After issuance, the validation record can stay or
# be deleted — CloudFront only checks at issuance.
###############################################################################

resource "aws_acm_certificate" "frontend" {
  domain_name       = var.domain_name
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }

  tags = {
    Project = var.name_prefix
    Phase   = "5J"
  }
}

###############################################################################
# S3 origin bucket — private, OAC-restricted, versioned, server-side encrypted.
#
# Public access is blocked at every layer (account-level + bucket-level).
# CloudFront reaches the bucket via OAC sigv4-signed requests; nothing else
# can read it.
###############################################################################

resource "aws_s3_bucket" "frontend" {
  bucket = var.bucket_name

  tags = {
    Project = var.name_prefix
    Phase   = "5J"
  }
}

resource "aws_s3_bucket_ownership_controls" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

###############################################################################
# CloudFront → S3 access via OAC (sigv4)
###############################################################################

resource "aws_cloudfront_origin_access_control" "frontend" {
  name                              = "${var.name_prefix}-frontend-oac"
  description                       = "OAC for ${var.name_prefix} frontend S3 bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

###############################################################################
# Response-headers policy (security hardening)
#
# Headers replicate the proven configuration from the spec; documented in
# ADR 014. CSP allowlists the API distribution origin in connect-src so the
# frontend's fetch() calls reach the API; img.mlbstatic.com is pre-allowed
# for the future "player headshot" polish item (harmless if unused).
#
# The Tailwind toolchain emits some inline <style> tags during dev/HMR; the
# 'unsafe-inline' on style-src tolerates that. If a future phase tightens
# this, it should validate via Content-Security-Policy-Report-Only first.
###############################################################################

locals {
  # Building the CSP via a multi-line list-then-join keeps it diff-friendly.
  #
  # Self-hosted fonts (Phase 5J): Inter and JetBrains Mono are bundled via
  # @fontsource imports in main.tsx instead of loaded from Google Fonts,
  # so neither fonts.googleapis.com (style-src) nor fonts.gstatic.com
  # (font-src) needs an allowlist. Eliminates a cross-origin critical-path
  # stall that pinned Lighthouse desktop at 76 — see ADR 014.
  csp_directives = [
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: https://img.mlbstatic.com",
    "connect-src 'self' ${var.api_origin}",
    "font-src 'self' data:",
    "object-src 'none'",
    "base-uri 'self'",
    "frame-ancestors 'none'",
  ]
  csp_header_value = join("; ", local.csp_directives)
}

resource "aws_cloudfront_response_headers_policy" "frontend" {
  name    = "${var.name_prefix}-frontend-security-headers"
  comment = "Strict security headers for the SPA. See ADR 014."

  security_headers_config {
    strict_transport_security {
      access_control_max_age_sec = 63072000
      include_subdomains         = true
      preload                    = true
      override                   = true
    }

    content_type_options {
      override = true
    }

    frame_options {
      frame_option = "DENY"
      override     = true
    }

    referrer_policy {
      referrer_policy = "strict-origin-when-cross-origin"
      override        = true
    }

    content_security_policy {
      content_security_policy = local.csp_header_value
      override                = true
    }
  }

  custom_headers_config {
    items {
      header   = "Permissions-Policy"
      value    = "geolocation=(), microphone=(), camera=(), payment=()"
      override = true
    }
  }
}

###############################################################################
# CloudFront distribution
#
# SPA fallback: a hard refresh on /compare or any client-side route returns
# the bucket's NoSuchKey 403 / 404; we rewrite both to /index.html @ 200 so
# React Router can pick up the path. Standard SPA hosting pattern.
###############################################################################

resource "aws_cloudfront_distribution" "frontend" {
  enabled             = true
  is_ipv6_enabled     = true
  http_version        = "http2and3"
  comment             = "${var.name_prefix} — SPA hosting (Phase 5J)"
  default_root_object = "index.html"
  price_class         = "PriceClass_100"
  retain_on_delete    = false
  wait_for_deployment = true

  aliases = [var.domain_name]

  origin {
    origin_id                = "${var.name_prefix}-frontend-s3"
    domain_name              = aws_s3_bucket.frontend.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.frontend.id
  }

  default_cache_behavior {
    target_origin_id           = "${var.name_prefix}-frontend-s3"
    viewer_protocol_policy     = "redirect-to-https"
    allowed_methods            = ["GET", "HEAD", "OPTIONS"]
    cached_methods             = ["GET", "HEAD"]
    compress                   = true
    cache_policy_id            = "658327ea-f89d-4fab-a63d-7e88639e58f6" # Managed-CachingOptimized
    response_headers_policy_id = aws_cloudfront_response_headers_policy.frontend.id
  }

  # SPA fallback — both 403 and 404 from S3 (private bucket + missing key)
  # rewrite to index.html so React Router can render the path.
  custom_error_response {
    error_code            = 403
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 10
  }

  custom_error_response {
    error_code            = 404
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 10
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    acm_certificate_arn      = aws_acm_certificate.frontend.arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }

  tags = {
    Project = var.name_prefix
    Phase   = "5J"
  }

  # The ACM cert must be ISSUED before the distribution can attach it.
  # Validation is a manual DNS step (Checkpoint #1); we depend_on the
  # cert resource so terraform still orders the create correctly.
  depends_on = [aws_acm_certificate.frontend]
}

###############################################################################
# S3 bucket policy — only the CloudFront distribution's OAC can read.
###############################################################################

data "aws_iam_policy_document" "frontend_bucket" {
  statement {
    sid       = "AllowCloudFrontOACRead"
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.frontend.arn}/*"]

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.frontend.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  policy = data.aws_iam_policy_document.frontend_bucket.json
}
