###############################################################################
# Account-level CloudWatch Logs role for API Gateway.
#
# WebSocket API (v2 WEBSOCKET) stages with access_log_settings require an
# account-level IAM role granting API Gateway permission to write to
# CloudWatch Logs. HTTP API (v2 HTTP) stages use service-linked logs and do
# not need this — which is why our existing HTTP API access logs work
# without it.
#
# This is a one-time-per-account configuration. Once set, every API Gateway
# in the account (REST, HTTP, WebSocket) can use access logs. Destroying
# this Terraform stack does NOT automatically reset the account setting.
###############################################################################

data "aws_iam_policy_document" "apigateway_logs_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["apigateway.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "apigateway_cloudwatch_logs" {
  name               = "${local.name_prefix}-apigateway-cloudwatch-logs"
  assume_role_policy = data.aws_iam_policy_document.apigateway_logs_assume.json
}

resource "aws_iam_role_policy_attachment" "apigateway_cloudwatch_logs" {
  role       = aws_iam_role.apigateway_cloudwatch_logs.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonAPIGatewayPushToCloudWatchLogs"
}

resource "aws_api_gateway_account" "this" {
  cloudwatch_role_arn = aws_iam_role.apigateway_cloudwatch_logs.arn
}
