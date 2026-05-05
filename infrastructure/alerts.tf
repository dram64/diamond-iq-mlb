###############################################################################
# Operational alerting — SNS topic + CloudWatch metric alarms.
#
# Scope: all three Lambdas (ingest, api, content). Each alarm publishes
# to the shared `aws_sns_topic.alerts` topic. Duration thresholds are
# set to ~80% of each function's configured timeout.
#
# Email subscription requires a one-time confirmation click in the inbox
# of `var.alert_email`. The email value is supplied via terraform.tfvars
# (gitignored) or TF_VAR_alert_email — never committed.
#
# IAM-propagation note: the deploy role's SNS and CloudWatch-alarm
# permissions live in `infrastructure/modules/oidc/main.tf`. On the
# first apply that introduces those permissions, the policy update and
# the resource creates here run in parallel — the SNS:CreateTopic call
# can race ahead of policy propagation and hit a transient 403. A
# re-run after the policy is committed always succeeds. No depends_on
# chain is wired here because the race is one-shot per permission set.
###############################################################################

resource "aws_sns_topic" "alerts" {
  name = "${local.name_prefix}-alerts"
}

resource "aws_sns_topic_subscription" "email_alerts" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
  # AWS rejects a subscription update that would re-trigger a confirm-email
  # for a previously-confirmed endpoint. Setting confirmation_timeout_in_minutes
  # high gives the human plenty of time to click the link after first deploy.
  confirmation_timeout_in_minutes = 60
}

# Allow CloudWatch alarms in this account to publish to the topic.
data "aws_iam_policy_document" "alerts_topic" {
  statement {
    effect    = "Allow"
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.alerts.arn]
    principals {
      type        = "Service"
      identifiers = ["cloudwatch.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "AWS:SourceAccount"
      values   = [local.account_id]
    }
  }
}

resource "aws_sns_topic_policy" "alerts" {
  arn    = aws_sns_topic.alerts.arn
  policy = data.aws_iam_policy_document.alerts_topic.json
}

###############################################################################
# Alarms — diamond-iq-generate-daily-content
###############################################################################

# (a) Any unhandled exception in a 5-minute window. The handler catches
# Bedrock and DynamoDB errors per-item, so this metric only goes up on
# truly-unexpected failures (import errors, missing env, etc.).
resource "aws_cloudwatch_metric_alarm" "content_errors" {
  alarm_name          = "${local.content_function_name}-errors"
  alarm_description   = "Unhandled exceptions in the daily content Lambda."
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  dimensions = {
    FunctionName = local.content_function_name
  }
  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

# (b) Duration approaching the 300s function timeout. 240,000 ms = 4 min.
resource "aws_cloudwatch_metric_alarm" "content_duration" {
  alarm_name          = "${local.content_function_name}-duration-near-timeout"
  alarm_description   = "Daily content Lambda took >4 min in a 5-min window (timeout is 5 min)."
  namespace           = "AWS/Lambda"
  metric_name         = "Duration"
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 240000
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  dimensions = {
    FunctionName = local.content_function_name
  }
  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

# (c) Custom metric: bedrock_failures > 0 over a 1-hour window. While the
# AWS daily-token quota is locked, this WILL fire on every scheduled tick
# until quota clears — that's the alarm doing its job.
resource "aws_cloudwatch_metric_alarm" "content_bedrock_failures" {
  alarm_name          = "${local.content_function_name}-bedrock-failures"
  alarm_description   = "Daily content Lambda is running but Bedrock invocations are failing."
  namespace           = "DiamondIQ/Content"
  metric_name         = "BedrockFailures"
  statistic           = "Sum"
  period              = 3600
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  dimensions = {
    LambdaFunction = local.content_function_name
  }
  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

# (d) Custom metric: dynamodb_failures > 0 over a 1-hour window.
resource "aws_cloudwatch_metric_alarm" "content_dynamodb_failures" {
  alarm_name          = "${local.content_function_name}-dynamodb-failures"
  alarm_description   = "Daily content Lambda generated content but DynamoDB writes failed."
  namespace           = "DiamondIQ/Content"
  metric_name         = "DynamoDBFailures"
  statistic           = "Sum"
  period              = 3600
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  dimensions = {
    LambdaFunction = local.content_function_name
  }
  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

# (e) Invocations <= 0 over a 24-hour window. EventBridge fires the Lambda
# 3x/day; a 24-hour zero-invocation window means EventBridge or the
# events-invoke IAM permission has broken. notBreaching on missing data
# avoids a false alarm during the first 24 hours after this alarm is created.
resource "aws_cloudwatch_metric_alarm" "content_invocations_zero" {
  alarm_name          = "${local.content_function_name}-invocations-zero"
  alarm_description   = "Daily content Lambda did not run in the last 24 hours — EventBridge schedule may be broken."
  namespace           = "AWS/Lambda"
  metric_name         = "Invocations"
  statistic           = "Sum"
  period              = 86400
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "LessThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  dimensions = {
    FunctionName = local.content_function_name
  }
  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

###############################################################################
# Alarms — diamond-iq-ingest-live-games (60s timeout, fires every minute)
###############################################################################

resource "aws_cloudwatch_metric_alarm" "ingest_errors" {
  alarm_name          = "${local.ingest_function_name}-errors"
  alarm_description   = "Unhandled exceptions in the ingest Lambda."
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  dimensions = {
    FunctionName = local.ingest_function_name
  }
  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

# 80% of the 60s timeout = 48,000 ms.
resource "aws_cloudwatch_metric_alarm" "ingest_duration" {
  alarm_name          = "${local.ingest_function_name}-duration-near-timeout"
  alarm_description   = "Ingest Lambda took >48s in a 5-min window (timeout is 60s)."
  namespace           = "AWS/Lambda"
  metric_name         = "Duration"
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 48000
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  dimensions = {
    FunctionName = local.ingest_function_name
  }
  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

# Ingest fires every minute → 60 invocations per hour expected. Zero
# invocations in a 1-hour window means EventBridge or the events-invoke
# IAM permission has broken. treat_missing_data = breaching because
# silence IS the failure mode here.
#
# MAINTENANCE NOTE: if the ingest schedule is paused intentionally
# (e.g., off-season hibernation, debug session), DISABLE this alarm
# first or it will fire within an hour and email someone.
resource "aws_cloudwatch_metric_alarm" "ingest_invocations_zero" {
  alarm_name          = "${local.ingest_function_name}-invocations-zero"
  alarm_description   = "Ingest Lambda did not run in the last hour — EventBridge schedule may be broken."
  namespace           = "AWS/Lambda"
  metric_name         = "Invocations"
  statistic           = "Sum"
  period              = 3600
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "LessThanOrEqualToThreshold"
  treat_missing_data  = "breaching"
  dimensions = {
    FunctionName = local.ingest_function_name
  }
  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

###############################################################################
# Alarms — diamond-iq-api-scoreboard (10s timeout, user-traffic-driven)
#
# No invocations-zero alarm: a portfolio API legitimately sees zero
# traffic for stretches and that's not a failure mode.
###############################################################################

resource "aws_cloudwatch_metric_alarm" "api_errors" {
  alarm_name          = "${local.api_function_name}-errors"
  alarm_description   = "Unhandled exceptions in the API Lambda."
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  dimensions = {
    FunctionName = local.api_function_name
  }
  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

# 80% of the 10s timeout = 8,000 ms. A cold start typically lands at
# 1-3s; 8s only fires on real hangs (DynamoDB outage, runaway loop).
resource "aws_cloudwatch_metric_alarm" "api_duration" {
  alarm_name          = "${local.api_function_name}-duration-near-timeout"
  alarm_description   = "API Lambda took >8s in a 5-min window (timeout is 10s)."
  namespace           = "AWS/Lambda"
  metric_name         = "Duration"
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 8000
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  dimensions = {
    FunctionName = local.api_function_name
  }
  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}
# Header touch to retrigger CI after fixing the ALERT_EMAIL secret.
# Header touch to re-trigger CI after the WAF/CloudFront IAM propagation race.
# Header touch to re-trigger CI for the WS API stage create that missed the first apply.
# Header touch to re-trigger CI after apigateway:UpdateAccount IAM propagation race.
# Header touch to re-trigger CI for stream-processor event source mapping create.
# Header touch to re-trigger CI after lambda:TagResource grant IAM propagation.
# Header touch to re-trigger CI after lambda:PutFunctionConcurrency grant IAM propagation.

###############################################################################
# Alarms — WAF (Security Layer Phase 1)
#
# CloudFront-scoped Web ACL metrics land in the AWS/WAFV2 namespace under
# Region=Global, regardless of where this Terraform applies from.
###############################################################################

# BlockedRequests > 1000 in a 1-hour window. Threshold is high deliberately —
# internet background scrape traffic comfortably fills the "any blocked"
# bucket; we only want to know about volume that suggests an active attack
# or rule misconfiguration.
resource "aws_cloudwatch_metric_alarm" "waf_blocked_requests" {
  alarm_name          = "${local.name_prefix}-waf-blocked-requests-spike"
  alarm_description   = "WAF blocked >1000 requests in the last hour — possible attack or false-positive flood."
  namespace           = "AWS/WAFV2"
  metric_name         = "BlockedRequests"
  statistic           = "Sum"
  period              = 3600
  evaluation_periods  = 1
  threshold           = 1000
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  dimensions = {
    WebACL = module.waf.web_acl_name
    Region = "Global"
    Rule   = "ALL"
  }
  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

# AllowedRequests anomaly band — fires if allowed-traffic volume drops
# (or spikes) sharply from its learned baseline. The 75% drop threshold from
# the spec is encoded as an anomaly-detection band rather than a fixed value
# because portfolio traffic is too low and irregular to set a meaningful
# absolute floor. Anomaly detection needs ~2 weeks of data to baseline; until
# then the alarm sits at INSUFFICIENT_DATA, which is not a breach.
resource "aws_cloudwatch_metric_alarm" "waf_allowed_requests_drop" {
  alarm_name          = "${local.name_prefix}-waf-allowed-requests-drop"
  alarm_description   = "WAF allowed-request volume fell sharply below baseline — possible over-blocking from a recent rule change."
  comparison_operator = "LessThanLowerThreshold"
  evaluation_periods  = 1
  threshold_metric_id = "ad1"
  treat_missing_data  = "notBreaching"

  metric_query {
    id          = "m1"
    return_data = true
    metric {
      namespace   = "AWS/WAFV2"
      metric_name = "AllowedRequests"
      period      = 3600
      stat        = "Sum"
      dimensions = {
        WebACL = module.waf.web_acl_name
        Region = "Global"
        Rule   = "ALL"
      }
    }
  }

  metric_query {
    id          = "ad1"
    expression  = "ANOMALY_DETECTION_BAND(m1, 4)"
    label       = "AllowedRequests (expected band)"
    return_data = true
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

###############################################################################
# Alarms — diamond-iq-stream-processor (Option 4: real-time pipeline)
###############################################################################

# Errors > 0 in 5-min window. Per-record errors are caught and logged
# inside the handler, so this only fires on truly unhandled exceptions
# (import errors, missing env, malformed event from AWS).
resource "aws_cloudwatch_metric_alarm" "stream_processor_errors" {
  alarm_name          = "${local.stream_processor_function_name}-errors"
  alarm_description   = "Unhandled exceptions in the stream-processor Lambda."
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  dimensions = {
    FunctionName = local.stream_processor_function_name
  }
  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

# IteratorAge > 60s means the processor is falling behind the stream.
# Sustained lag means a record-level slowdown (e.g., slow PostToConnection
# fan-out) or a poison record bisecting repeatedly.
resource "aws_cloudwatch_metric_alarm" "stream_processor_iterator_age" {
  alarm_name          = "${local.stream_processor_function_name}-iterator-age"
  alarm_description   = "Stream-processor IteratorAge exceeded 60s — pipeline is falling behind."
  namespace           = "AWS/Lambda"
  metric_name         = "IteratorAge"
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 60000
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  dimensions = {
    FunctionName = local.stream_processor_function_name
  }
  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

# Concurrent WebSocket connection count. Mostly aspirational at portfolio
# scale (we expect <10 concurrent), but worth wiring so a future scale
# event surfaces with an email instead of a surprise bill. Uses the
# AWS/ApiGateway metric for WebSocket APIs which is cohort-by-stage.
resource "aws_cloudwatch_metric_alarm" "ws_connection_count" {
  alarm_name          = "${local.name_prefix}-ws-connections-high"
  alarm_description   = "WebSocket concurrent connection count exceeded 1000."
  namespace           = "AWS/ApiGateway"
  metric_name         = "ConnectCount"
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1000
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  dimensions = {
    ApiId = aws_apigatewayv2_api.ws.id
    Stage = aws_apigatewayv2_stage.ws.name
  }
  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

###############################################################################
# Alarms — Cost-runaway protection (ADR 013)
#
# Two classes:
#   1. Per-function: Invocations > 10_000 / 1-hr window. ~20x peak
#      portfolio rate; only fires on a stuck-loop / runaway scenario.
#   2. Account-wide: ConcurrentExecutions > 50. Catches a runaway
#      that escapes per-function reserved_concurrent_executions
#      (e.g., a misconfiguration that drops the reservation, or a
#      future Lambda that ships without one).
###############################################################################

locals {
  cost_runaway_lambdas = toset([
    local.ingest_function_name,
    local.api_function_name,
    local.content_function_name,
    local.ws_connect_function_name,
    local.ws_disconnect_function_name,
    local.ws_default_function_name,
    local.stream_processor_function_name,
    local.ingest_players_function_name,
    local.ingest_daily_stats_function_name,
    local.compute_advanced_stats_function_name,
    local.api_players_function_name,
    local.ingest_standings_function_name,
    local.ingest_hardest_hit_function_name,
    local.ingest_team_stats_function_name,
    local.ingest_player_awards_function_name,
    local.ai_compare_function_name,
    local.ingest_statcast_function_name,
    "${local.name_prefix}-test-bedrock",
  ])
}

resource "aws_cloudwatch_metric_alarm" "lambda_runaway_invocations" {
  for_each = local.cost_runaway_lambdas

  alarm_name          = "${each.key}-runaway-invocations"
  alarm_description   = "Lambda invoked >10000 times in the last hour — possible runaway loop or recursive trigger."
  namespace           = "AWS/Lambda"
  metric_name         = "Invocations"
  statistic           = "Sum"
  period              = 3600
  evaluation_periods  = 1
  threshold           = 10000
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  dimensions = {
    FunctionName = each.key
  }
  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

# Account-wide ConcurrentExecutions ceiling. Catches concurrency spikes
# even if a single function's reservation is missing or wrong. 50 is
# well above expected portfolio peak (~10 across all 8 functions
# combined under normal traffic).
resource "aws_cloudwatch_metric_alarm" "account_concurrent_executions_high" {
  alarm_name          = "${local.name_prefix}-account-concurrent-executions-high"
  alarm_description   = "Account-wide Lambda ConcurrentExecutions exceeded 50 — runaway concurrency across one or more functions."
  namespace           = "AWS/Lambda"
  metric_name         = "ConcurrentExecutions"
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 50
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
}

###############################################################################
# Alarms — diamond-iq-ingest-players (Option 5 Phase 5B)
#
# Note: deliberately no invocations-zero alarm for the WEEKLY rate(7 days)
# schedule. CloudWatch metric-alarm period caps at 86400s (1 day), so an
# 8-day evaluation window would require evaluation_periods=8 with breach-
# on-missing-data — the math works but the alarm fires noisy on legitimate
# weekly cadence. The daily-rosters invocations-zero alarm below covers
# the more important signal (the daily cadence is the one users notice if
# it stops).
###############################################################################

resource "aws_cloudwatch_metric_alarm" "ingest_players_errors" {
  alarm_name          = "${local.ingest_players_function_name}-errors"
  alarm_description   = "Unhandled exceptions in the player-ingest Lambda."
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  dimensions = {
    FunctionName = local.ingest_players_function_name
  }
  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

# 80% of the 300s timeout = 240,000 ms.
resource "aws_cloudwatch_metric_alarm" "ingest_players_duration" {
  alarm_name          = "${local.ingest_players_function_name}-duration-near-timeout"
  alarm_description   = "Player ingest Lambda took >4 min in a 5-min window (timeout is 5 min)."
  namespace           = "AWS/Lambda"
  metric_name         = "Duration"
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 240000
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  dimensions = {
    FunctionName = local.ingest_players_function_name
  }
  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

# Daily roster cron should produce one Invocations/day. A 24-hour zero
# means the daily EventBridge rule or its target is broken. notBreaching
# on missing data avoids a false alarm in the first 24h after creation.
resource "aws_cloudwatch_metric_alarm" "ingest_players_daily_invocations_zero" {
  alarm_name          = "${local.ingest_players_function_name}-daily-rosters-invocations-zero"
  alarm_description   = "Player-ingest Lambda did not run in the last 24 hours — daily roster EventBridge schedule may be broken."
  namespace           = "AWS/Lambda"
  metric_name         = "Invocations"
  statistic           = "Sum"
  period              = 86400
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "LessThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  dimensions = {
    FunctionName = local.ingest_players_function_name
  }
  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

###############################################################################
# Alarms — diamond-iq-ingest-daily-stats (Option 5 Phase 5C)
###############################################################################

resource "aws_cloudwatch_metric_alarm" "ingest_daily_stats_errors" {
  alarm_name          = "${local.ingest_daily_stats_function_name}-errors"
  alarm_description   = "Unhandled exceptions in the daily-stats ingest Lambda."
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  dimensions = {
    FunctionName = local.ingest_daily_stats_function_name
  }
  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

# 80% of the 300s timeout = 240,000 ms.
resource "aws_cloudwatch_metric_alarm" "ingest_daily_stats_duration" {
  alarm_name          = "${local.ingest_daily_stats_function_name}-duration-near-timeout"
  alarm_description   = "Daily-stats ingest Lambda took >4 min in a 5-min window (timeout is 5 min)."
  namespace           = "AWS/Lambda"
  metric_name         = "Duration"
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 240000
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  dimensions = {
    FunctionName = local.ingest_daily_stats_function_name
  }
  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

# Daily 09:00 UTC cron should produce one Invocations/day. A 24-hour zero
# means the EventBridge rule or its target is broken.
resource "aws_cloudwatch_metric_alarm" "ingest_daily_stats_invocations_zero" {
  alarm_name          = "${local.ingest_daily_stats_function_name}-invocations-zero"
  alarm_description   = "Daily-stats ingest Lambda did not run in the last 24 hours — EventBridge schedule may be broken."
  namespace           = "AWS/Lambda"
  metric_name         = "Invocations"
  statistic           = "Sum"
  period              = 86400
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "LessThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  dimensions = {
    FunctionName = local.ingest_daily_stats_function_name
  }
  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

###############################################################################
# Alarms — diamond-iq-compute-advanced-stats (Option 5 Phase 5D)
###############################################################################

resource "aws_cloudwatch_metric_alarm" "compute_advanced_stats_errors" {
  alarm_name          = "${local.compute_advanced_stats_function_name}-errors"
  alarm_description   = "Unhandled exceptions in the advanced-stats compute Lambda."
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  dimensions = {
    FunctionName = local.compute_advanced_stats_function_name
  }
  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

# 80% of the 60s timeout = 48,000 ms.
resource "aws_cloudwatch_metric_alarm" "compute_advanced_stats_duration" {
  alarm_name          = "${local.compute_advanced_stats_function_name}-duration-near-timeout"
  alarm_description   = "Advanced-stats compute Lambda took >48s in a 5-min window (timeout is 60s)."
  namespace           = "AWS/Lambda"
  metric_name         = "Duration"
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 48000
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  dimensions = {
    FunctionName = local.compute_advanced_stats_function_name
  }
  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

# Daily 09:30 UTC cron should produce one Invocations/day.
resource "aws_cloudwatch_metric_alarm" "compute_advanced_stats_invocations_zero" {
  alarm_name          = "${local.compute_advanced_stats_function_name}-invocations-zero"
  alarm_description   = "Advanced-stats compute Lambda did not run in the last 24 hours — EventBridge schedule may be broken."
  namespace           = "AWS/Lambda"
  metric_name         = "Invocations"
  statistic           = "Sum"
  period              = 86400
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "LessThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  dimensions = {
    FunctionName = local.compute_advanced_stats_function_name
  }
  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

###############################################################################
# Alarms — diamond-iq-api-players (Option 5 Phase 5E)
###############################################################################

resource "aws_cloudwatch_metric_alarm" "api_players_errors" {
  alarm_name          = "${local.api_players_function_name}-errors"
  alarm_description   = "Unhandled exceptions in the player API Lambda."
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  dimensions = {
    FunctionName = local.api_players_function_name
  }
  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

# 80% of the 10s timeout = 8,000 ms. A request consistently approaching
# timeout signals DynamoDB degradation or a missing-data full-table scan.
resource "aws_cloudwatch_metric_alarm" "api_players_duration" {
  alarm_name          = "${local.api_players_function_name}-duration-near-timeout"
  alarm_description   = "Player API Lambda took >8s in a 5-min window (timeout is 10s)."
  namespace           = "AWS/Lambda"
  metric_name         = "Duration"
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 8000
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  dimensions = {
    FunctionName = local.api_players_function_name
  }
  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

# Sustained 4xx rate signals frontend bug, scraper, or path-typo storm.
resource "aws_cloudwatch_metric_alarm" "api_players_4xx_rate" {
  alarm_name          = "${local.api_players_function_name}-4xx-rate"
  alarm_description   = "API Gateway 4XX count exceeded 5/min sustained — frontend bug or scraper."
  namespace           = "AWS/ApiGateway"
  metric_name         = "4xx"
  statistic           = "Sum"
  period              = 60
  evaluation_periods  = 5
  threshold           = 5
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  dimensions = {
    ApiId = module.api_gateway.api_id
  }
  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

###############################################################################
# Alarms — diamond-iq-ingest-standings (Option 5 Phase 5L)
###############################################################################

resource "aws_cloudwatch_metric_alarm" "ingest_standings_errors" {
  alarm_name          = "${local.ingest_standings_function_name}-errors"
  alarm_description   = "Unhandled exceptions in the standings ingest Lambda."
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  dimensions = {
    FunctionName = local.ingest_standings_function_name
  }
  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

# 80% of 60s timeout = 48,000 ms.
resource "aws_cloudwatch_metric_alarm" "ingest_standings_duration" {
  alarm_name          = "${local.ingest_standings_function_name}-duration-near-timeout"
  alarm_description   = "Standings ingest Lambda took >48s in a 5-min window (timeout is 60s)."
  namespace           = "AWS/Lambda"
  metric_name         = "Duration"
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 48000
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  dimensions = {
    FunctionName = local.ingest_standings_function_name
  }
  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "ingest_standings_invocations_zero" {
  alarm_name          = "${local.ingest_standings_function_name}-invocations-zero"
  alarm_description   = "Standings ingest Lambda did not run in the last 24 hours."
  namespace           = "AWS/Lambda"
  metric_name         = "Invocations"
  statistic           = "Sum"
  period              = 86400
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "LessThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  dimensions = {
    FunctionName = local.ingest_standings_function_name
  }
  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

###############################################################################
# Alarms — diamond-iq-ingest-hardest-hit (Option 5 Phase 5L)
###############################################################################

resource "aws_cloudwatch_metric_alarm" "ingest_hardest_hit_errors" {
  alarm_name          = "${local.ingest_hardest_hit_function_name}-errors"
  alarm_description   = "Unhandled exceptions in the hardest-hit ingest Lambda."
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  dimensions = {
    FunctionName = local.ingest_hardest_hit_function_name
  }
  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

# 80% of 300s timeout = 240,000 ms.
resource "aws_cloudwatch_metric_alarm" "ingest_hardest_hit_duration" {
  alarm_name          = "${local.ingest_hardest_hit_function_name}-duration-near-timeout"
  alarm_description   = "Hardest-hit ingest Lambda took >4 min in a 5-min window (timeout is 5 min)."
  namespace           = "AWS/Lambda"
  metric_name         = "Duration"
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 240000
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  dimensions = {
    FunctionName = local.ingest_hardest_hit_function_name
  }
  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "ingest_hardest_hit_invocations_zero" {
  alarm_name          = "${local.ingest_hardest_hit_function_name}-invocations-zero"
  alarm_description   = "Hardest-hit ingest Lambda did not run in the last 24 hours."
  namespace           = "AWS/Lambda"
  metric_name         = "Invocations"
  statistic           = "Sum"
  period              = 86400
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "LessThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  dimensions = {
    FunctionName = local.ingest_hardest_hit_function_name
  }
  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

###############################################################################
# Alarms — diamond-iq-ingest-team-stats (Option 5 Phase 5L final)
###############################################################################

resource "aws_cloudwatch_metric_alarm" "ingest_team_stats_errors" {
  alarm_name          = "${local.ingest_team_stats_function_name}-errors"
  alarm_description   = "Unhandled exceptions in the team-stats ingest Lambda."
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  dimensions = {
    FunctionName = local.ingest_team_stats_function_name
  }
  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

# 80% of 60s timeout = 48,000 ms.
resource "aws_cloudwatch_metric_alarm" "ingest_team_stats_duration" {
  alarm_name          = "${local.ingest_team_stats_function_name}-duration-near-timeout"
  alarm_description   = "Team-stats ingest Lambda took >48s in a 5-min window (timeout is 60s)."
  namespace           = "AWS/Lambda"
  metric_name         = "Duration"
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 48000
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  dimensions = {
    FunctionName = local.ingest_team_stats_function_name
  }
  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "ingest_team_stats_invocations_zero" {
  alarm_name          = "${local.ingest_team_stats_function_name}-invocations-zero"
  alarm_description   = "Team-stats ingest Lambda did not run in the last 24 hours."
  namespace           = "AWS/Lambda"
  metric_name         = "Invocations"
  statistic           = "Sum"
  period              = 86400
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "LessThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  dimensions = {
    FunctionName = local.ingest_team_stats_function_name
  }
  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

###############################################################################
# Alarms — diamond-iq-ingest-player-awards (Phase 6)
###############################################################################

resource "aws_cloudwatch_metric_alarm" "ingest_player_awards_errors" {
  alarm_name          = "${local.ingest_player_awards_function_name}-errors"
  alarm_description   = "Unhandled exceptions in the player-awards ingest Lambda."
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  dimensions = {
    FunctionName = local.ingest_player_awards_function_name
  }
  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

# 80% of 300s timeout = 240,000 ms.
resource "aws_cloudwatch_metric_alarm" "ingest_player_awards_duration" {
  alarm_name          = "${local.ingest_player_awards_function_name}-duration-near-timeout"
  alarm_description   = "Awards ingest Lambda took >240s in a 5-min window (timeout is 300s)."
  namespace           = "AWS/Lambda"
  metric_name         = "Duration"
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 240000
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  dimensions = {
    FunctionName = local.ingest_player_awards_function_name
  }
  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

# Weekly cron — alarm if no invocation in 7 days. (CloudWatch caps period
# × evaluation_periods at 604800 / 7 days when period >= 3600.)
resource "aws_cloudwatch_metric_alarm" "ingest_player_awards_invocations_zero" {
  alarm_name          = "${local.ingest_player_awards_function_name}-invocations-zero"
  alarm_description   = "Awards ingest Lambda did not run in the last 7 days (weekly cron)."
  namespace           = "AWS/Lambda"
  metric_name         = "Invocations"
  statistic           = "Sum"
  period              = 86400 # 1 day
  evaluation_periods  = 7
  threshold           = 0
  comparison_operator = "LessThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  dimensions = {
    FunctionName = local.ingest_player_awards_function_name
  }
  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

###############################################################################
# Alarms — diamond-iq-ai-compare (Phase 6)
#
# Errors-only alarm. Throttle-induced 502s are user-facing but expected
# during quota resets, so we don't alarm on InvocationErrors. The cost-
# runaway alarm above protects against an accidental unbounded loop.
###############################################################################

resource "aws_cloudwatch_metric_alarm" "ai_compare_errors" {
  alarm_name          = "${local.ai_compare_function_name}-errors"
  alarm_description   = "Unhandled exceptions in the AI-compare Lambda."
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  dimensions = {
    FunctionName = local.ai_compare_function_name
  }
  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

###############################################################################
# Alarms — diamond-iq-ingest-statcast (Phase 7)
###############################################################################

resource "aws_cloudwatch_metric_alarm" "ingest_statcast_errors" {
  alarm_name          = "${local.ingest_statcast_function_name}-errors"
  alarm_description   = "Unhandled exceptions in the Statcast ingest Lambda."
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  dimensions = {
    FunctionName = local.ingest_statcast_function_name
  }
  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

# 80% of 60s timeout = 48,000 ms.
resource "aws_cloudwatch_metric_alarm" "ingest_statcast_duration" {
  alarm_name          = "${local.ingest_statcast_function_name}-duration-near-timeout"
  alarm_description   = "Statcast ingest took >48s in a 5-min window (timeout is 60s)."
  namespace           = "AWS/Lambda"
  metric_name         = "Duration"
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 48000
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  dimensions = {
    FunctionName = local.ingest_statcast_function_name
  }
  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

# Daily cron — alarm if no invocation in 2 days (gives 1 day of headroom
# in case the cron fires near midnight and CloudWatch's bucket alignment
# wobbles).
resource "aws_cloudwatch_metric_alarm" "ingest_statcast_invocations_zero" {
  alarm_name          = "${local.ingest_statcast_function_name}-invocations-zero"
  alarm_description   = "Statcast ingest Lambda did not run in the last 2 days (daily cron)."
  namespace           = "AWS/Lambda"
  metric_name         = "Invocations"
  statistic           = "Sum"
  period              = 86400 # 1 day
  evaluation_periods  = 2
  threshold           = 0
  comparison_operator = "LessThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  dimensions = {
    FunctionName = local.ingest_statcast_function_name
  }
  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}
