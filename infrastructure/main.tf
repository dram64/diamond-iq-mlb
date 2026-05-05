###############################################################################
# Diamond IQ — main infrastructure stack.
#
# Deploys: DynamoDB games table, two Lambda functions (ingest + API),
# API Gateway HTTP API, EventBridge 1-minute schedule, GitHub OIDC
# deploy role.
#
# State lives in S3 (created by infrastructure/bootstrap/).
###############################################################################

terraform {
  required_version = ">= 1.7"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }

  backend "s3" {
    bucket         = "diamond-iq-tfstate-334856751632"
    key            = "main/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "diamond-iq-tfstate-locks"
    encrypt        = true
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "diamond-iq"
      ManagedBy   = "terraform"
      Environment = var.environment
    }
  }
}

data "aws_caller_identity" "current" {}

locals {
  account_id               = data.aws_caller_identity.current.account_id
  name_prefix              = "diamond-iq"
  games_table_name         = "${local.name_prefix}-games"
  connections_table_name   = "${local.name_prefix}-connections"
  ingest_function_name     = "${local.name_prefix}-ingest-live-games"
  api_function_name        = "${local.name_prefix}-api-scoreboard"
  content_function_name    = "${local.name_prefix}-generate-daily-content"
  api_name                 = "${local.name_prefix}-api"
  ingest_rule_name         = "${local.name_prefix}-ingest-schedule"
  github_deploy_role       = "${local.name_prefix}-github-deploy"
  state_bucket_name        = "diamond-iq-tfstate-${local.account_id}"
  lock_table_name          = "diamond-iq-tfstate-locks"
  shared_dir               = "${path.module}/../functions/shared"
  ingest_source_dir        = "${path.module}/../functions/ingest_live_games"
  api_source_dir           = "${path.module}/../functions/api_scoreboard"
  content_source_dir       = "${path.module}/../functions/generate_daily_content"
  ws_connect_source_dir    = "${path.module}/../functions/ws_connect"
  ws_disconnect_source_dir = "${path.module}/../functions/ws_disconnect"
  ws_default_source_dir    = "${path.module}/../functions/ws_default"

  ws_connect_function_name    = "${local.name_prefix}-ws-connect"
  ws_disconnect_function_name = "${local.name_prefix}-ws-disconnect"
  ws_default_function_name    = "${local.name_prefix}-ws-default"

  stream_processor_source_dir    = "${path.module}/../functions/stream_processor"
  stream_processor_function_name = "${local.name_prefix}-stream-processor"

  ingest_players_source_dir    = "${path.module}/../functions/ingest_players"
  ingest_players_function_name = "${local.name_prefix}-ingest-players"
  ingest_players_weekly_rule   = "${local.name_prefix}-ingest-players-weekly"
  ingest_players_daily_rule    = "${local.name_prefix}-ingest-rosters-daily"

  ingest_daily_stats_source_dir    = "${path.module}/../functions/ingest_daily_stats"
  ingest_daily_stats_function_name = "${local.name_prefix}-ingest-daily-stats"
  ingest_daily_stats_rule          = "${local.name_prefix}-ingest-daily-stats-cron"

  compute_advanced_stats_source_dir    = "${path.module}/../functions/compute_advanced_stats"
  compute_advanced_stats_function_name = "${local.name_prefix}-compute-advanced-stats"
  compute_advanced_stats_rule          = "${local.name_prefix}-compute-advanced-stats-cron"

  api_players_source_dir    = "${path.module}/../functions/api_players"
  api_players_function_name = "${local.name_prefix}-api-players"

  ingest_standings_source_dir    = "${path.module}/../functions/ingest_standings"
  ingest_standings_function_name = "${local.name_prefix}-ingest-standings"
  ingest_standings_rule          = "${local.name_prefix}-ingest-standings-cron"

  ingest_hardest_hit_source_dir    = "${path.module}/../functions/ingest_hardest_hit"
  ingest_hardest_hit_function_name = "${local.name_prefix}-ingest-hardest-hit"
  ingest_hardest_hit_rule          = "${local.name_prefix}-ingest-hardest-hit-cron"

  ingest_team_stats_source_dir    = "${path.module}/../functions/ingest_team_stats"
  ingest_team_stats_function_name = "${local.name_prefix}-ingest-team-stats"
  ingest_team_stats_rule          = "${local.name_prefix}-ingest-team-stats-cron"

  # ── Phase 6 ──────────────────────────────────────────────────────────
  ingest_player_awards_source_dir    = "${path.module}/../functions/ingest_player_awards"
  ingest_player_awards_function_name = "${local.name_prefix}-ingest-player-awards"
  ingest_player_awards_rule          = "${local.name_prefix}-ingest-player-awards-cron"

  ai_compare_source_dir    = "${path.module}/../functions/ai_compare"
  ai_compare_function_name = "${local.name_prefix}-ai-compare"

  # ── Phase 7 ──────────────────────────────────────────────────────────
  ingest_statcast_source_dir    = "${path.module}/../functions/ingest_statcast"
  ingest_statcast_function_name = "${local.name_prefix}-ingest-statcast"
  ingest_statcast_rule          = "${local.name_prefix}-ingest-statcast-cron"

  # 15:00, 16:00, 17:00 UTC — three idempotent triggers per day. The
  # first tick generates content; later ticks no-op via the handler's
  # existing-SK check, but stand by to fill in any items the earlier
  # tick missed (Bedrock throttle, transient DynamoDB error, etc.).
  content_schedule_hours_utc = [15, 16, 17]
}

###############################################################################
# DynamoDB
###############################################################################

module "dynamodb" {
  source     = "./modules/dynamodb"
  table_name = local.games_table_name
}

###############################################################################
# DynamoDB connections table — backs the WebSocket pipeline (Option 4).
#
# Composite key:
#   PK = connection_id           (the API Gateway WebSocket connection id)
#   SK = "META"                  (the connection record itself)
#      | "GAME#<game_pk>"        (one row per per-game subscription)
#
# GSI "by-game":
#   PK = game_pk_str             (string-typed game_pk for GSI)
#   SK = connection_id           (back-reference to the connection)
#
# The META row holds the WebSocket endpoint metadata
# (domain_name + stage + connected_at_utc) the stream processor needs to
# build PostToConnection calls. Subscription rows project sparsely to the
# GSI — META rows have no game_pk_str attribute and stay out of the GSI.
#
# TTL is 4 hours from connect time on every row, so a client that drops
# without sending $disconnect cleans up automatically.
###############################################################################

resource "aws_dynamodb_table" "connections" {
  name         = local.connections_table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "PK"
  range_key    = "SK"

  attribute {
    name = "PK"
    type = "S"
  }

  attribute {
    name = "SK"
    type = "S"
  }

  attribute {
    name = "game_pk_str"
    type = "S"
  }

  global_secondary_index {
    name            = "by-game"
    hash_key        = "game_pk_str"
    range_key       = "PK"
    projection_type = "ALL"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  server_side_encryption {
    enabled = true
  }
}

###############################################################################
# Ingest Lambda — write access to the games table only.
###############################################################################

data "aws_iam_policy_document" "ingest_policy" {
  statement {
    effect = "Allow"
    actions = [
      "dynamodb:PutItem",
      "dynamodb:DescribeTable",
    ]
    resources = [module.dynamodb.table_arn]
  }
}

module "lambda_ingest" {
  source = "./modules/lambda"

  function_name = local.ingest_function_name
  handler       = "handler.lambda_handler"
  source_dir    = local.ingest_source_dir
  shared_dir    = local.shared_dir

  environment_variables = {
    GAMES_TABLE_NAME = module.dynamodb.table_name
  }

  timeout             = 60
  memory_size         = 512
  iam_policy_document = data.aws_iam_policy_document.ingest_policy.json
}

###############################################################################
# API Lambda — read-only access to the games table.
###############################################################################

data "aws_iam_policy_document" "api_policy" {
  statement {
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:Query",
    ]
    resources = [module.dynamodb.table_arn]
  }
}

module "lambda_api" {
  source = "./modules/lambda"

  function_name = local.api_function_name
  handler       = "handler.lambda_handler"
  source_dir    = local.api_source_dir
  shared_dir    = local.shared_dir

  environment_variables = {
    GAMES_TABLE_NAME = module.dynamodb.table_name
  }

  timeout             = 10
  memory_size         = 256
  iam_policy_document = data.aws_iam_policy_document.api_policy.json
}

###############################################################################
# API Gateway HTTP API
###############################################################################

module "api_gateway" {
  source = "./modules/api-gateway"

  api_name              = local.api_name
  api_lambda_name       = module.lambda_api.function_name
  api_lambda_invoke_arn = module.lambda_api.invoke_arn
  # Phase 5J: full allow-list (production frontend + localhost dev ports).
  # The Vite dev-server proxy (Phase 5F follow-up) is still the recommended
  # local-dev path; these origins exist so direct fetch from the browser at
  # localhost:5173-5176 also works without the proxy.
  cors_allow_origins = var.cors_allow_origins
}

###############################################################################
# Content-generation Lambda — read games, write content items, call Bedrock.
#
# Bedrock invocation is allowed against the same cross-region inference profile
# the 9A smoke-test Lambda used. The IAM policy must list both the profile ARN
# and the underlying foundation-model ARNs in every region the profile may
# route to (us-east-1, us-east-2, us-west-2).
###############################################################################

# NOTE: `local.bedrock_inference_profile_id`, `_arn`, and
# `bedrock_foundation_model_arns` are defined in `test_bedrock_stub.tf`. We
# intentionally reference the same values here so that the 9A smoke-test
# stub and the 9C content Lambda share one source of truth for the model
# ID. When the 9A stub is removed at close-out, those locals must be
# moved into this file as part of that cleanup commit.

data "aws_iam_policy_document" "content_policy" {
  statement {
    sid    = "GamesAndContentTableAccess"
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:Query",
    ]
    resources = [module.dynamodb.table_arn]
  }

  statement {
    sid     = "BedrockInvokeClaudeSonnet46"
    effect  = "Allow"
    actions = ["bedrock:InvokeModel"]
    resources = concat(
      [local.bedrock_inference_profile_arn],
      local.bedrock_foundation_model_arns,
    )
  }

  # Custom CloudWatch metrics. PutMetricData has no resource-level ARNs; we
  # scope to our namespace via a condition so this Lambda can't pollute
  # other namespaces.
  statement {
    sid       = "PublishCustomMetricsToDiamondIQContent"
    effect    = "Allow"
    actions   = ["cloudwatch:PutMetricData"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "cloudwatch:namespace"
      values   = ["DiamondIQ/Content"]
    }
  }
}

module "lambda_content" {
  source = "./modules/lambda"

  function_name = local.content_function_name
  handler       = "handler.lambda_handler"
  source_dir    = local.content_source_dir
  shared_dir    = local.shared_dir

  environment_variables = {
    GAMES_TABLE_NAME = module.dynamodb.table_name
    BEDROCK_MODEL_ID = local.bedrock_inference_profile_id
  }

  timeout             = 300
  memory_size         = 512
  iam_policy_document = data.aws_iam_policy_document.content_policy.json
}

resource "aws_cloudwatch_event_rule" "content_schedule" {
  for_each = toset([for h in local.content_schedule_hours_utc : tostring(h)])

  name                = "${local.name_prefix}-content-${each.key}-utc"
  description         = "Daily content generation trigger at ${each.key}:00 UTC."
  schedule_expression = "cron(0 ${each.key} * * ? *)"
  state               = "ENABLED"
}

resource "aws_cloudwatch_event_target" "content_lambda" {
  for_each = aws_cloudwatch_event_rule.content_schedule

  rule      = each.value.name
  target_id = "content-lambda"
  arn       = module.lambda_content.function_arn
}

resource "aws_lambda_permission" "content_events_invoke" {
  for_each = aws_cloudwatch_event_rule.content_schedule

  statement_id  = "AllowEventBridgeInvoke-${each.key}"
  action        = "lambda:InvokeFunction"
  function_name = module.lambda_content.function_name
  principal     = "events.amazonaws.com"
  source_arn    = each.value.arn
}

###############################################################################
# EventBridge schedule for the ingest Lambda
###############################################################################

module "events" {
  source = "./modules/events"

  rule_name          = local.ingest_rule_name
  ingest_lambda_name = module.lambda_ingest.function_name
  ingest_lambda_arn  = module.lambda_ingest.function_arn
}

###############################################################################
# WebSocket Lambdas — connect, disconnect, default (subscribe/unsubscribe).
#
# Each gets minimum-privilege DynamoDB on the connections table only.
# connect needs PutItem (META row); disconnect needs Query + DeleteItem
# (find all rows for connection, delete each); default needs PutItem (subscribe)
# and DeleteItem (unsubscribe).
###############################################################################

data "aws_iam_policy_document" "ws_connect_policy" {
  statement {
    effect    = "Allow"
    actions   = ["dynamodb:PutItem"]
    resources = [aws_dynamodb_table.connections.arn]
  }
}

module "lambda_ws_connect" {
  source = "./modules/lambda"

  function_name = local.ws_connect_function_name
  handler       = "handler.lambda_handler"
  source_dir    = local.ws_connect_source_dir
  shared_dir    = local.shared_dir

  environment_variables = {
    CONNECTIONS_TABLE_NAME = aws_dynamodb_table.connections.name
  }

  timeout             = 5
  memory_size         = 128
  iam_policy_document = data.aws_iam_policy_document.ws_connect_policy.json
}

data "aws_iam_policy_document" "ws_disconnect_policy" {
  statement {
    effect    = "Allow"
    actions   = ["dynamodb:Query", "dynamodb:DeleteItem"]
    resources = [aws_dynamodb_table.connections.arn]
  }
}

module "lambda_ws_disconnect" {
  source = "./modules/lambda"

  function_name = local.ws_disconnect_function_name
  handler       = "handler.lambda_handler"
  source_dir    = local.ws_disconnect_source_dir
  shared_dir    = local.shared_dir

  environment_variables = {
    CONNECTIONS_TABLE_NAME = aws_dynamodb_table.connections.name
  }

  timeout             = 5
  memory_size         = 128
  iam_policy_document = data.aws_iam_policy_document.ws_disconnect_policy.json
}

data "aws_iam_policy_document" "ws_default_policy" {
  statement {
    effect    = "Allow"
    actions   = ["dynamodb:PutItem", "dynamodb:DeleteItem"]
    resources = [aws_dynamodb_table.connections.arn]
  }
}

module "lambda_ws_default" {
  source = "./modules/lambda"

  function_name = local.ws_default_function_name
  handler       = "handler.lambda_handler"
  source_dir    = local.ws_default_source_dir
  shared_dir    = local.shared_dir

  environment_variables = {
    CONNECTIONS_TABLE_NAME = aws_dynamodb_table.connections.name
  }

  timeout             = 5
  memory_size         = 128
  iam_policy_document = data.aws_iam_policy_document.ws_default_policy.json
}

###############################################################################
# Player ingest Lambda (Option 5 Phase 5B). Two cron schedules drive it:
#   * weekly  — full mode: teams + rosters + bulk player metadata
#   * daily   — roster_only: teams + rosters (rosters churn daily on
#               IL moves, trades, call-ups; metadata is stable enough
#               for weekly refresh)
# A single Lambda handles both modes via the EventBridge payload.
###############################################################################

data "aws_iam_policy_document" "ingest_players_policy" {
  statement {
    sid    = "DynamoDBPlayersWrite"
    effect = "Allow"
    actions = [
      "dynamodb:PutItem",
      "dynamodb:BatchWriteItem",
    ]
    resources = [module.dynamodb.table_arn]
  }

  statement {
    sid       = "PublishPlayersMetrics"
    effect    = "Allow"
    actions   = ["cloudwatch:PutMetricData"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "cloudwatch:namespace"
      values   = ["DiamondIQ/Players"]
    }
  }
}

module "lambda_ingest_players" {
  source = "./modules/lambda"

  function_name = local.ingest_players_function_name
  handler       = "handler.lambda_handler"
  source_dir    = local.ingest_players_source_dir
  shared_dir    = local.shared_dir

  environment_variables = {
    GAMES_TABLE_NAME = module.dynamodb.table_name
  }

  timeout             = 300
  memory_size         = 512
  iam_policy_document = data.aws_iam_policy_document.ingest_players_policy.json
}

resource "aws_cloudwatch_event_rule" "ingest_players_weekly" {
  name                = local.ingest_players_weekly_rule
  description         = "Weekly full-metadata refresh for player + roster ingest."
  schedule_expression = "rate(7 days)"
  state               = "ENABLED"
}

resource "aws_cloudwatch_event_target" "ingest_players_weekly" {
  rule      = aws_cloudwatch_event_rule.ingest_players_weekly.name
  target_id = "ingest-players-weekly"
  arn       = module.lambda_ingest_players.function_arn
  input     = jsonencode({ mode = "full" })
}

resource "aws_lambda_permission" "ingest_players_weekly_invoke" {
  statement_id  = "AllowEventBridgeInvokeWeekly"
  action        = "lambda:InvokeFunction"
  function_name = module.lambda_ingest_players.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.ingest_players_weekly.arn
}

resource "aws_cloudwatch_event_rule" "ingest_rosters_daily" {
  name                = local.ingest_players_daily_rule
  description         = "Daily roster-only refresh; tracks IL moves, trades, call-ups."
  schedule_expression = "cron(0 12 * * ? *)" # 12:00 UTC daily
  state               = "ENABLED"
}

resource "aws_cloudwatch_event_target" "ingest_rosters_daily" {
  rule      = aws_cloudwatch_event_rule.ingest_rosters_daily.name
  target_id = "ingest-rosters-daily"
  arn       = module.lambda_ingest_players.function_arn
  input     = jsonencode({ mode = "roster_only" })
}

resource "aws_lambda_permission" "ingest_rosters_daily_invoke" {
  statement_id  = "AllowEventBridgeInvokeDaily"
  action        = "lambda:InvokeFunction"
  function_name = module.lambda_ingest_players.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.ingest_rosters_daily.arn
}

###############################################################################
# Daily player stats ingest Lambda (Option 5 Phase 5C).
# - Triggered nightly at 09:00 UTC (after all West Coast games are Final).
# - Reads yesterday's Final games from the MLB schedule API, fetches each
#   boxscore, writes per-game DAILYSTATS rows + bulk-refreshes qualified
#   season records.
# - Same single-Lambda-multiple-modes pattern as ingest-players (mode is
#   "standard" for the cron and "season_only" for ad-hoc backfills).
###############################################################################

data "aws_iam_policy_document" "ingest_daily_stats_policy" {
  statement {
    sid    = "DynamoDBDailyStatsReadWrite"
    effect = "Allow"
    actions = [
      "dynamodb:Query",
      "dynamodb:PutItem",
      "dynamodb:BatchWriteItem",
    ]
    resources = [module.dynamodb.table_arn]
  }

  statement {
    sid       = "PublishDailyStatsMetrics"
    effect    = "Allow"
    actions   = ["cloudwatch:PutMetricData"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "cloudwatch:namespace"
      values   = ["DiamondIQ/DailyStats"]
    }
  }
}

module "lambda_ingest_daily_stats" {
  source = "./modules/lambda"

  function_name = local.ingest_daily_stats_function_name
  handler       = "handler.lambda_handler"
  source_dir    = local.ingest_daily_stats_source_dir
  shared_dir    = local.shared_dir

  environment_variables = {
    GAMES_TABLE_NAME = module.dynamodb.table_name
  }

  timeout             = 300
  memory_size         = 512
  iam_policy_document = data.aws_iam_policy_document.ingest_daily_stats_policy.json
}

resource "aws_cloudwatch_event_rule" "ingest_daily_stats" {
  name                = local.ingest_daily_stats_rule
  description         = "Daily player stats ingest at 09:00 UTC (post late-game completion)."
  schedule_expression = "cron(0 9 * * ? *)"
  state               = "ENABLED"
}

resource "aws_cloudwatch_event_target" "ingest_daily_stats" {
  rule      = aws_cloudwatch_event_rule.ingest_daily_stats.name
  target_id = "ingest-daily-stats"
  arn       = module.lambda_ingest_daily_stats.function_arn
  input     = jsonencode({ mode = "standard" })
}

resource "aws_lambda_permission" "ingest_daily_stats_invoke" {
  statement_id  = "AllowEventBridgeInvokeDailyStats"
  action        = "lambda:InvokeFunction"
  function_name = module.lambda_ingest_daily_stats.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.ingest_daily_stats.arn
}

###############################################################################
# Computed advanced stats Lambda (Option 5 Phase 5D).
# - Triggered nightly at 09:30 UTC, 30 minutes after Phase 5C populates fresh
#   season records.
# - Reads STATS#<season>#<group> records, computes wOBA / OPS+ / FIP per
#   player, writes back via UpdateItem (no overwrite of upstream fields).
# - League means and cFIP backsolved from our own qualified-player aggregates.
###############################################################################

data "aws_iam_policy_document" "compute_advanced_stats_policy" {
  statement {
    sid    = "DynamoDBAdvancedStatsReadWrite"
    effect = "Allow"
    actions = [
      "dynamodb:Query",
      "dynamodb:UpdateItem",
    ]
    resources = [module.dynamodb.table_arn]
  }

  statement {
    sid       = "PublishAdvancedStatsMetrics"
    effect    = "Allow"
    actions   = ["cloudwatch:PutMetricData"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "cloudwatch:namespace"
      values   = ["DiamondIQ/AdvancedStats"]
    }
  }
}

module "lambda_compute_advanced_stats" {
  source = "./modules/lambda"

  function_name = local.compute_advanced_stats_function_name
  handler       = "handler.lambda_handler"
  source_dir    = local.compute_advanced_stats_source_dir
  shared_dir    = local.shared_dir

  environment_variables = {
    GAMES_TABLE_NAME = module.dynamodb.table_name
  }

  timeout             = 60
  memory_size         = 256
  iam_policy_document = data.aws_iam_policy_document.compute_advanced_stats_policy.json
}

resource "aws_cloudwatch_event_rule" "compute_advanced_stats" {
  name                = local.compute_advanced_stats_rule
  description         = "Daily wOBA/OPS+/FIP compute at 09:30 UTC, 30 min after the daily-stats ingest."
  schedule_expression = "cron(30 9 * * ? *)"
  state               = "ENABLED"
}

resource "aws_cloudwatch_event_target" "compute_advanced_stats" {
  rule      = aws_cloudwatch_event_rule.compute_advanced_stats.name
  target_id = "compute-advanced-stats"
  arn       = module.lambda_compute_advanced_stats.function_arn
}

resource "aws_lambda_permission" "compute_advanced_stats_invoke" {
  statement_id  = "AllowEventBridgeInvokeAdvancedStats"
  action        = "lambda:InvokeFunction"
  function_name = module.lambda_compute_advanced_stats.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.compute_advanced_stats.arn
}

###############################################################################
# Player API Lambda (Option 5 Phase 5E).
# - Single Lambda, route-based dispatch on event["routeKey"].
# - 6 endpoints registered as separate API Gateway routes with one shared
#   AWS_PROXY integration.
# - CloudFront stays as-is (caching disabled by design); per-endpoint
#   Cache-Control headers in the Lambda response are honored by browsers
#   only. See ADR 012 Phase 5E amendment.
###############################################################################

data "aws_iam_policy_document" "api_players_policy" {
  statement {
    sid    = "DynamoDBPlayersRead"
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:BatchGetItem",
      "dynamodb:Query",
    ]
    resources = [module.dynamodb.table_arn]
  }

  statement {
    sid       = "PublishPlayerAPIMetrics"
    effect    = "Allow"
    actions   = ["cloudwatch:PutMetricData"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "cloudwatch:namespace"
      values   = ["DiamondIQ/PlayerAPI"]
    }
  }
}

module "lambda_api_players" {
  source = "./modules/lambda"

  function_name = local.api_players_function_name
  handler       = "handler.lambda_handler"
  source_dir    = local.api_players_source_dir
  shared_dir    = local.shared_dir

  environment_variables = {
    GAMES_TABLE_NAME = module.dynamodb.table_name
  }

  timeout             = 10
  memory_size         = 256
  iam_policy_document = data.aws_iam_policy_document.api_players_policy.json
}

resource "aws_apigatewayv2_integration" "api_players" {
  api_id                 = module.api_gateway.api_id
  integration_type       = "AWS_PROXY"
  integration_uri        = module.lambda_api_players.invoke_arn
  payload_format_version = "2.0"
}

# Six routes share one integration. Compare is registered before the
# {personId} pattern in human-review order; API Gateway HTTP API v2 routes
# literal-segment-priority at runtime regardless of declaration order.
resource "aws_apigatewayv2_route" "api_players_compare" {
  api_id    = module.api_gateway.api_id
  route_key = "GET /api/players/compare"
  target    = "integrations/${aws_apigatewayv2_integration.api_players.id}"
}

resource "aws_apigatewayv2_route" "api_players_get" {
  api_id    = module.api_gateway.api_id
  route_key = "GET /api/players/{personId}"
  target    = "integrations/${aws_apigatewayv2_integration.api_players.id}"
}

resource "aws_apigatewayv2_route" "api_leaders" {
  api_id    = module.api_gateway.api_id
  route_key = "GET /api/leaders/{group}/{stat}"
  target    = "integrations/${aws_apigatewayv2_integration.api_players.id}"
}

resource "aws_apigatewayv2_route" "api_team_roster" {
  api_id    = module.api_gateway.api_id
  route_key = "GET /api/teams/{teamId}/roster"
  target    = "integrations/${aws_apigatewayv2_integration.api_players.id}"
}

# Phase 5L — team-aggregate stats. Compare route registered before the
# {teamId} parameterized routes in human-review order; API Gateway HTTP API
# v2 routes literal-segment-priority at runtime regardless of declaration.
resource "aws_apigatewayv2_route" "api_team_compare" {
  api_id    = module.api_gateway.api_id
  route_key = "GET /api/teams/compare"
  target    = "integrations/${aws_apigatewayv2_integration.api_players.id}"
}

resource "aws_apigatewayv2_route" "api_team_stats" {
  api_id    = module.api_gateway.api_id
  route_key = "GET /api/teams/{teamId}/stats"
  target    = "integrations/${aws_apigatewayv2_integration.api_players.id}"
}

resource "aws_apigatewayv2_route" "api_standings" {
  api_id    = module.api_gateway.api_id
  route_key = "GET /api/standings/{season}"
  target    = "integrations/${aws_apigatewayv2_integration.api_players.id}"
}

resource "aws_apigatewayv2_route" "api_hardest_hit" {
  api_id    = module.api_gateway.api_id
  route_key = "GET /api/hardest-hit/{date}"
  target    = "integrations/${aws_apigatewayv2_integration.api_players.id}"
}

resource "aws_lambda_permission" "api_players_apigw_invoke" {
  statement_id  = "AllowAPIGatewayInvokePlayerAPI"
  action        = "lambda:InvokeFunction"
  function_name = module.lambda_api_players.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${module.api_gateway.execution_arn}/*/*"
}

###############################################################################
# Standings ingest Lambda (Option 5 Phase 5L).
# - Triggered nightly at 09:15 UTC, between Phase 5C (09:00) and 5D (09:30).
# - One MLB API call returns 6 divisions × 5 teams = 30 STANDINGS rows.
# - Idempotent: every run overwrites the partition with fresh upstream data.
###############################################################################

data "aws_iam_policy_document" "ingest_standings_policy" {
  statement {
    sid    = "DynamoDBStandingsWrite"
    effect = "Allow"
    actions = [
      "dynamodb:PutItem",
      "dynamodb:BatchWriteItem",
    ]
    resources = [module.dynamodb.table_arn]
  }

  statement {
    sid       = "PublishStandingsMetrics"
    effect    = "Allow"
    actions   = ["cloudwatch:PutMetricData"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "cloudwatch:namespace"
      values   = ["DiamondIQ/Standings"]
    }
  }
}

module "lambda_ingest_standings" {
  source = "./modules/lambda"

  function_name = local.ingest_standings_function_name
  handler       = "handler.lambda_handler"
  source_dir    = local.ingest_standings_source_dir
  shared_dir    = local.shared_dir

  environment_variables = {
    GAMES_TABLE_NAME = module.dynamodb.table_name
  }

  timeout             = 60
  memory_size         = 256
  iam_policy_document = data.aws_iam_policy_document.ingest_standings_policy.json
}

resource "aws_cloudwatch_event_rule" "ingest_standings" {
  name                = local.ingest_standings_rule
  description         = "Daily standings refresh at 09:15 UTC."
  schedule_expression = "cron(15 9 * * ? *)"
  state               = "ENABLED"
}

resource "aws_cloudwatch_event_target" "ingest_standings" {
  rule      = aws_cloudwatch_event_rule.ingest_standings.name
  target_id = "ingest-standings"
  arn       = module.lambda_ingest_standings.function_arn
}

resource "aws_lambda_permission" "ingest_standings_invoke" {
  statement_id  = "AllowEventBridgeInvokeStandings"
  action        = "lambda:InvokeFunction"
  function_name = module.lambda_ingest_standings.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.ingest_standings.arn
}

###############################################################################
# Hardest-hit ingest Lambda (Option 5 Phase 5L).
# - Triggered nightly at 09:45 UTC, after Phase 5D (09:30) so feed/live data
#   is settled.
# - Walks every Final game from yesterday, parses playEvents[].hitData,
#   writes the top 25 by exit velocity into HITS#<date>.
###############################################################################

data "aws_iam_policy_document" "ingest_hardest_hit_policy" {
  statement {
    sid    = "DynamoDBHardestHitWrite"
    effect = "Allow"
    actions = [
      "dynamodb:PutItem",
      "dynamodb:BatchWriteItem",
    ]
    resources = [module.dynamodb.table_arn]
  }

  statement {
    sid       = "PublishHardestHitMetrics"
    effect    = "Allow"
    actions   = ["cloudwatch:PutMetricData"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "cloudwatch:namespace"
      values   = ["DiamondIQ/HardestHit"]
    }
  }
}

module "lambda_ingest_hardest_hit" {
  source = "./modules/lambda"

  function_name = local.ingest_hardest_hit_function_name
  handler       = "handler.lambda_handler"
  source_dir    = local.ingest_hardest_hit_source_dir
  shared_dir    = local.shared_dir

  environment_variables = {
    GAMES_TABLE_NAME = module.dynamodb.table_name
  }

  timeout             = 300
  memory_size         = 512
  iam_policy_document = data.aws_iam_policy_document.ingest_hardest_hit_policy.json
}

resource "aws_cloudwatch_event_rule" "ingest_hardest_hit" {
  name                = local.ingest_hardest_hit_rule
  description         = "Daily hardest-hit ingest at 09:45 UTC."
  schedule_expression = "cron(45 9 * * ? *)"
  state               = "ENABLED"
}

resource "aws_cloudwatch_event_target" "ingest_hardest_hit" {
  rule      = aws_cloudwatch_event_rule.ingest_hardest_hit.name
  target_id = "ingest-hardest-hit"
  arn       = module.lambda_ingest_hardest_hit.function_arn
}

resource "aws_lambda_permission" "ingest_hardest_hit_invoke" {
  statement_id  = "AllowEventBridgeInvokeHardestHit"
  action        = "lambda:InvokeFunction"
  function_name = module.lambda_ingest_hardest_hit.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.ingest_hardest_hit.arn
}

###############################################################################
# Team-aggregate stats ingest Lambda (Option 5 Phase 5L final).
# - Daily 09:20 UTC cron, sandwiched between standings (09:15) and
#   compute-advanced-stats (09:30). 30 MLB API calls + 30 PutItems.
# - Writes TEAMSTATS#<season>/TEAMSTATS#<teamId> rows holding hitting +
#   pitching aggregates — used by /api/teams/{teamId}/stats and
#   /api/teams/compare endpoints.
# - Idempotent. No TTL — daily overwrite in place.
###############################################################################

data "aws_iam_policy_document" "ingest_team_stats_policy" {
  statement {
    sid    = "DynamoDBTeamStatsWrite"
    effect = "Allow"
    actions = [
      "dynamodb:PutItem",
      "dynamodb:BatchWriteItem",
    ]
    resources = [module.dynamodb.table_arn]
  }

  statement {
    sid       = "PublishTeamStatsMetrics"
    effect    = "Allow"
    actions   = ["cloudwatch:PutMetricData"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "cloudwatch:namespace"
      values   = ["DiamondIQ/TeamStats"]
    }
  }
}

module "lambda_ingest_team_stats" {
  source = "./modules/lambda"

  function_name = local.ingest_team_stats_function_name
  handler       = "handler.lambda_handler"
  source_dir    = local.ingest_team_stats_source_dir
  shared_dir    = local.shared_dir

  environment_variables = {
    GAMES_TABLE_NAME = module.dynamodb.table_name
  }

  timeout             = 60
  memory_size         = 256
  iam_policy_document = data.aws_iam_policy_document.ingest_team_stats_policy.json
}

resource "aws_cloudwatch_event_rule" "ingest_team_stats" {
  name                = local.ingest_team_stats_rule
  description         = "Daily team-aggregate stats refresh at 09:20 UTC."
  schedule_expression = "cron(20 9 * * ? *)"
  state               = "ENABLED"
}

resource "aws_cloudwatch_event_target" "ingest_team_stats" {
  rule      = aws_cloudwatch_event_rule.ingest_team_stats.name
  target_id = "ingest-team-stats"
  arn       = module.lambda_ingest_team_stats.function_arn
}

resource "aws_lambda_permission" "ingest_team_stats_invoke" {
  statement_id  = "AllowEventBridgeInvokeTeamStats"
  action        = "lambda:InvokeFunction"
  function_name = module.lambda_ingest_team_stats.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.ingest_team_stats.arn
}

###############################################################################
# Phase 6 — ingest-player-awards (career awards / hardware) Lambda
#
# Walks every PLAYER#GLOBAL row, hits MLB's /people/{id}/awards endpoint,
# filters to the MLB-tier allowlist (MVP, Cy Young, AS, GG, SS, ROY, WSC),
# aggregates per-category counts + years, writes AWARDS#GLOBAL/AWARDS#<id>
# rows. Weekly cron (Sundays 08:00 UTC) — awards change at most yearly.
###############################################################################

data "aws_iam_policy_document" "ingest_player_awards_policy" {
  statement {
    sid    = "DynamoDBAwardsRW"
    effect = "Allow"
    actions = [
      "dynamodb:Query",
      "dynamodb:PutItem",
      "dynamodb:BatchWriteItem",
    ]
    resources = [module.dynamodb.table_arn]
  }

  statement {
    sid       = "PublishAwardsMetrics"
    effect    = "Allow"
    actions   = ["cloudwatch:PutMetricData"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "cloudwatch:namespace"
      values   = ["DiamondIQ/PlayerAwards"]
    }
  }
}

module "lambda_ingest_player_awards" {
  source = "./modules/lambda"

  function_name = local.ingest_player_awards_function_name
  handler       = "handler.lambda_handler"
  source_dir    = local.ingest_player_awards_source_dir
  shared_dir    = local.shared_dir

  environment_variables = {
    GAMES_TABLE_NAME = module.dynamodb.table_name
  }

  # ~779 player_ids × (~1 MLB API call + ~1 PutItem) at 50 ms inter-call
  # sleep ≈ 80 s. 300 s timeout gives 4× headroom for slow MLB responses.
  timeout             = 300
  memory_size         = 512
  iam_policy_document = data.aws_iam_policy_document.ingest_player_awards_policy.json
}

resource "aws_cloudwatch_event_rule" "ingest_player_awards" {
  name                = local.ingest_player_awards_rule
  description         = "Weekly career-awards refresh, Sundays 08:00 UTC."
  schedule_expression = "cron(0 8 ? * SUN *)"
  state               = "ENABLED"
}

resource "aws_cloudwatch_event_target" "ingest_player_awards" {
  rule      = aws_cloudwatch_event_rule.ingest_player_awards.name
  target_id = "ingest-player-awards"
  arn       = module.lambda_ingest_player_awards.function_arn
}

resource "aws_lambda_permission" "ingest_player_awards_invoke" {
  statement_id  = "AllowEventBridgeInvokeAwards"
  action        = "lambda:InvokeFunction"
  function_name = module.lambda_ingest_player_awards.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.ingest_player_awards.arn
}

###############################################################################
# Phase 6 — ai-compare (Bedrock-backed comparison commentary) Lambda
#
# Two routes funnel here:
#   GET /api/compare-analysis/players?ids=<csv>
#   GET /api/compare-analysis/teams?ids=<csv>
#
# Read-through cache via AIANALYSIS#<kind>#<season>#<sorted-ids> rows with
# 7-day TTL. Bedrock model id is env-var-injected so we can swap Haiku
# 3.5 / 4.5 without re-deploying the Lambda code.
###############################################################################

data "aws_iam_policy_document" "ai_compare_policy" {
  # DynamoDB read for source data + cache check + cache write.
  statement {
    sid    = "DynamoDBCompareReadWrite"
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:Query",
      "dynamodb:PutItem",
    ]
    resources = [module.dynamodb.table_arn]
  }

  # Bedrock invocation. Scoped to the Anthropic Claude family on
  # us-east-1 + us-east-2 + us-west-2 (cross-region inference profile
  # spans those three).
  statement {
    sid    = "BedrockInvokeAnthropic"
    effect = "Allow"
    actions = [
      "bedrock:InvokeModel",
    ]
    resources = [
      "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-5-haiku-20241022-v1:0",
      "arn:aws:bedrock:us-east-2::foundation-model/anthropic.claude-3-5-haiku-20241022-v1:0",
      "arn:aws:bedrock:us-west-2::foundation-model/anthropic.claude-3-5-haiku-20241022-v1:0",
      "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0",
      "arn:aws:bedrock:us-east-2::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0",
      "arn:aws:bedrock:us-west-2::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0",
      "arn:aws:bedrock:*:*:inference-profile/us.anthropic.claude-3-5-haiku-20241022-v1:0",
      "arn:aws:bedrock:*:*:inference-profile/us.anthropic.claude-haiku-4-5-20251001-v1:0",
    ]
  }

  statement {
    sid       = "PublishAICompareMetrics"
    effect    = "Allow"
    actions   = ["cloudwatch:PutMetricData"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "cloudwatch:namespace"
      values   = ["DiamondIQ/AICompare"]
    }
  }
}

module "lambda_ai_compare" {
  source = "./modules/lambda"

  function_name = local.ai_compare_function_name
  handler       = "handler.lambda_handler"
  source_dir    = local.ai_compare_source_dir
  shared_dir    = local.shared_dir

  environment_variables = {
    GAMES_TABLE_NAME = module.dynamodb.table_name
    BEDROCK_MODEL_ID = "us.anthropic.claude-3-5-haiku-20241022-v1:0"
  }

  # 30 s timeout: Bedrock Haiku typically replies in 1-3 s, but 4-player
  # / large-input requests can take longer; 10× p50 headroom is safe.
  timeout             = 30
  memory_size         = 512
  iam_policy_document = data.aws_iam_policy_document.ai_compare_policy.json
}

resource "aws_apigatewayv2_integration" "ai_compare" {
  api_id                 = module.api_gateway.api_id
  integration_type       = "AWS_PROXY"
  integration_uri        = module.lambda_ai_compare.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_lambda_permission" "ai_compare_apigw" {
  statement_id  = "AllowAPIGatewayInvokeAICompare"
  action        = "lambda:InvokeFunction"
  function_name = module.lambda_ai_compare.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${module.api_gateway.execution_arn}/*/*"
}

resource "aws_apigatewayv2_route" "api_compare_analysis_players" {
  api_id    = module.api_gateway.api_id
  route_key = "GET /api/compare-analysis/players"
  target    = "integrations/${aws_apigatewayv2_integration.ai_compare.id}"
}

resource "aws_apigatewayv2_route" "api_compare_analysis_teams" {
  api_id    = module.api_gateway.api_id
  route_key = "GET /api/compare-analysis/teams"
  target    = "integrations/${aws_apigatewayv2_integration.ai_compare.id}"
}

###############################################################################
# Phase 6 — extra api_players routes
#
# /api/players/search — typeahead substring scan over PLAYER#GLOBAL.
# /api/featured-matchup — deterministic daily-rotating wOBA pair.
###############################################################################

resource "aws_apigatewayv2_route" "api_players_search" {
  api_id    = module.api_gateway.api_id
  route_key = "GET /api/players/search"
  target    = "integrations/${aws_apigatewayv2_integration.api_players.id}"
}

resource "aws_apigatewayv2_route" "api_featured_matchup" {
  api_id    = module.api_gateway.api_id
  route_key = "GET /api/featured-matchup"
  target    = "integrations/${aws_apigatewayv2_integration.api_players.id}"
}

# Phase 8.5 Track 1 — today's featured game (real schedule).
resource "aws_apigatewayv2_route" "api_games_featured" {
  api_id    = module.api_gateway.api_id
  route_key = "GET /api/games/featured"
  target    = "integrations/${aws_apigatewayv2_integration.api_players.id}"
}

###############################################################################
# Phase 7 — ingest-statcast (Baseball Savant) Lambda
#
# Daily 09:30 UTC cron (after standings @ 09:15 + team-stats @ 09:20).
# Pulls 5 CSV leaderboards from baseballsavant.mlb.com, joins by player_id,
# writes one merged STATCAST#<season>/STATCAST#<personId> row per player.
# See ADR 016 for endpoint + storage rationale.
###############################################################################

data "aws_iam_policy_document" "ingest_statcast_policy" {
  statement {
    sid    = "DynamoDBStatcastWrite"
    effect = "Allow"
    actions = [
      "dynamodb:PutItem",
      "dynamodb:BatchWriteItem",
    ]
    resources = [module.dynamodb.table_arn]
  }

  statement {
    sid       = "PublishStatcastMetrics"
    effect    = "Allow"
    actions   = ["cloudwatch:PutMetricData"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "cloudwatch:namespace"
      values   = ["DiamondIQ/Statcast"]
    }
  }
}

module "lambda_ingest_statcast" {
  source = "./modules/lambda"

  function_name = local.ingest_statcast_function_name
  handler       = "handler.lambda_handler"
  source_dir    = local.ingest_statcast_source_dir
  shared_dir    = local.shared_dir

  environment_variables = {
    GAMES_TABLE_NAME = module.dynamodb.table_name
  }

  # 5 sequential CSV downloads (~0.4 s each) + parse + ~200 PutItems.
  # Step 0 estimate: ~5-10 s end-to-end. 60 s gives 6× headroom for
  # slow Savant responses or transient retries.
  timeout             = 60
  memory_size         = 256
  iam_policy_document = data.aws_iam_policy_document.ingest_statcast_policy.json
}

resource "aws_cloudwatch_event_rule" "ingest_statcast" {
  name                = local.ingest_statcast_rule
  description         = "Daily Statcast / Baseball Savant refresh at 09:30 UTC."
  schedule_expression = "cron(30 9 * * ? *)"
  state               = "ENABLED"
}

resource "aws_cloudwatch_event_target" "ingest_statcast" {
  rule      = aws_cloudwatch_event_rule.ingest_statcast.name
  target_id = "ingest-statcast"
  arn       = module.lambda_ingest_statcast.function_arn
}

resource "aws_lambda_permission" "ingest_statcast_invoke" {
  statement_id  = "AllowEventBridgeInvokeStatcast"
  action        = "lambda:InvokeFunction"
  function_name = module.lambda_ingest_statcast.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.ingest_statcast.arn
}

###############################################################################
# Stream-processor Lambda — fans out DynamoDB Streams MODIFYs to subscribed
# WebSocket clients via the API Gateway Management API.
#
# Trigger: DynamoDB Streams from the games table. Diff old vs new image,
# query connections by-game GSI, parallel PostToConnection. 410 Gone on
# any connection deletes that connection's rows from the table.
###############################################################################

data "aws_iam_policy_document" "stream_processor_policy" {
  # Stream consumption — scoped to the games-table stream.
  statement {
    sid    = "DynamoDBStreamConsume"
    effect = "Allow"
    actions = [
      "dynamodb:GetRecords",
      "dynamodb:GetShardIterator",
      "dynamodb:DescribeStream",
    ]
    resources = [module.dynamodb.stream_arn]
  }

  # ListStreams accepts no resource scoping. Filtering happens at runtime.
  statement {
    sid       = "DynamoDBListStreams"
    effect    = "Allow"
    actions   = ["dynamodb:ListStreams"]
    resources = ["*"]
  }

  # Connections-table read (GSI Query) and stale-connection cleanup.
  statement {
    sid    = "DynamoDBConnectionsAccess"
    effect = "Allow"
    actions = [
      "dynamodb:Query",
      "dynamodb:DeleteItem",
    ]
    resources = [
      aws_dynamodb_table.connections.arn,
      "${aws_dynamodb_table.connections.arn}/index/by-game",
    ]
  }

  # PostToConnection on the WebSocket API. The wildcard at the end covers
  # every connection id under the production stage.
  statement {
    sid       = "WebSocketManageConnections"
    effect    = "Allow"
    actions   = ["execute-api:ManageConnections"]
    resources = ["arn:aws:execute-api:${var.aws_region}:${local.account_id}:${aws_apigatewayv2_api.ws.id}/${aws_apigatewayv2_stage.ws.name}/POST/@connections/*"]
  }

  # Send poison-record reports to the DLQ. The Lambda execution role is the
  # principal AWS uses for the destination-config delivery; queue policies
  # are NOT consulted on this path.
  statement {
    sid       = "SqsSendToDlq"
    effect    = "Allow"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.stream_processor_dlq.arn]
  }
}

# Cost-protection DLQ for the stream-processor's event source mapping.
# Records that fail after maximum_retry_attempts (5) or exceed
# maximum_record_age_in_seconds (3600) land here for human inspection.
# At portfolio scale we don't expect this queue to ever receive a message;
# the alarm on QueueDepth (future polish) would notify if one arrives.
resource "aws_sqs_queue" "stream_processor_dlq" {
  name                       = "${local.name_prefix}-stream-processor-dlq"
  visibility_timeout_seconds = 300
  message_retention_seconds  = 14 * 24 * 60 * 60 # 14 days
  sqs_managed_sse_enabled    = true
}

module "lambda_stream_processor" {
  source = "./modules/lambda"

  function_name = local.stream_processor_function_name
  handler       = "handler.lambda_handler"
  source_dir    = local.stream_processor_source_dir
  shared_dir    = local.shared_dir

  environment_variables = {
    CONNECTIONS_TABLE_NAME = aws_dynamodb_table.connections.name
    WEBSOCKET_API_ENDPOINT = "https://${aws_apigatewayv2_api.ws.id}.execute-api.${var.aws_region}.amazonaws.com/${aws_apigatewayv2_stage.ws.name}"
  }

  timeout             = 30
  memory_size         = 256
  iam_policy_document = data.aws_iam_policy_document.stream_processor_policy.json
}

resource "aws_lambda_event_source_mapping" "stream_processor" {
  event_source_arn                   = module.dynamodb.stream_arn
  function_name                      = module.lambda_stream_processor.function_arn
  starting_position                  = "LATEST"
  batch_size                         = 10
  maximum_batching_window_in_seconds = 1
  parallelization_factor             = 10
  bisect_batch_on_function_error     = true

  # Cost-runaway protections (ADR 013). The defaults of -1 / -1 are
  # "retry forever, no max age" — exactly the cost-spiral shape we want
  # to bound. After 5 attempts or 1 hour, the record goes to the DLQ
  # and the shard moves on.
  maximum_retry_attempts        = 5
  maximum_record_age_in_seconds = 3600

  destination_config {
    on_failure {
      destination_arn = aws_sqs_queue.stream_processor_dlq.arn
    }
  }
}

###############################################################################
# WAF (Security Layer Phase 1) — fronts the API Gateway via CloudFront.
#
# WAFv2 cannot attach to API Gateway HTTP API directly (only REST API).
# CloudFront is the standard pattern that unlocks WAF for HTTP API origins;
# see infrastructure/cloudfront.tf for the distribution.
###############################################################################

module "waf" {
  source = "./modules/waf"

  name_prefix          = local.name_prefix
  scope                = "CLOUDFRONT"
  managed_rule_actions = var.managed_rule_actions
  rate_limit_default   = var.rate_limit_default
  rate_limit_sensitive = var.rate_limit_sensitive
  enable_geo_blocking  = var.enable_geo_blocking
  blocked_countries    = var.blocked_countries
  blocked_user_agents  = var.blocked_user_agents
  dev_allow_list_cidrs = var.dev_allow_list_cidrs
}

###############################################################################
# GitHub Actions OIDC deploy role
###############################################################################

module "oidc" {
  source = "./modules/oidc"

  github_repo       = var.github_repo
  role_name         = local.github_deploy_role
  name_prefix       = local.name_prefix
  account_id        = local.account_id
  aws_region        = var.aws_region
  state_bucket_name = local.state_bucket_name
  lock_table_name   = local.lock_table_name
}

###############################################################################
# Frontend hosting (Phase 5J).
# - Sibling distribution to the existing API CloudFront. Serves the React SPA
#   from a private S3 bucket via OAC.
# - Cloudflare proxied DNS (orange cloud) provides edge WAF/DDoS for free —
#   no AWS WAF on this distribution. See ADR 014.
# - DNS is manual; Terraform produces the validation CNAME and the final
#   distribution domain. The Cloudflare records are added by hand.
###############################################################################

module "frontend_hosting" {
  source = "./modules/frontend_hosting"

  name_prefix = local.name_prefix
  domain_name = var.frontend_domain_name
  bucket_name = var.frontend_bucket_name
  api_origin  = "https://d17hrttnkrygh8.cloudfront.net"
}

###############################################################################
# Extend the OIDC deploy role so the frontend-deploy workflow can sync the
# bucket and invalidate the new CloudFront distribution. The existing
# CloudFront permissions in modules/oidc/main.tf already cover Get/List/
# CreateInvalidation by virtue of being unscoped (CloudFront IAM doesn't
# accept resource ARNs), so the only NEW grant we need is s3:* scoped to
# the new bucket.
###############################################################################

data "aws_iam_policy_document" "frontend_deploy_extra" {
  statement {
    sid    = "FrontendBucketDeploy"
    effect = "Allow"
    actions = [
      "s3:ListBucket",
      "s3:GetBucketLocation",
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
    ]
    resources = [
      module.frontend_hosting.bucket_arn,
      "${module.frontend_hosting.bucket_arn}/*",
    ]
  }

  # CloudFront invalidations don't accept resource-level scoping in IAM.
  # The base OIDC policy already grants the unscoped CloudFront actions
  # (cloudfront:CreateDistribution etc.); we add CreateInvalidation here
  # specifically because it's missing from the base policy.
  statement {
    sid       = "FrontendDistributionInvalidate"
    effect    = "Allow"
    actions   = ["cloudfront:CreateInvalidation"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "frontend_deploy_extra" {
  name   = "${local.github_deploy_role}-frontend-extra"
  role   = module.oidc.deploy_role_name
  policy = data.aws_iam_policy_document.frontend_deploy_extra.json
}
