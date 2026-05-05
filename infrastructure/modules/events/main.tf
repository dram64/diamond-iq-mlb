###############################################################################
# 1-minute EventBridge schedule that fires the ingest Lambda.
#
# The ingest handler self-throttles on slates with no live games, so running
# 24/7 at this rate stays well within free-tier and burns ~43k Lambda
# invocations / month.
###############################################################################

resource "aws_cloudwatch_event_rule" "ingest_schedule" {
  name                = var.rule_name
  description         = "Fires the ingest Lambda every minute."
  schedule_expression = "rate(1 minute)"
  state               = "ENABLED"
}

resource "aws_cloudwatch_event_target" "ingest_lambda" {
  rule      = aws_cloudwatch_event_rule.ingest_schedule.name
  target_id = "ingest-lambda"
  arn       = var.ingest_lambda_arn
}

resource "aws_lambda_permission" "events_invoke" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = var.ingest_lambda_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.ingest_schedule.arn
}
