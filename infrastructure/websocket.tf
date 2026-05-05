###############################################################################
# WebSocket API Gateway — fans real-time game updates out to browser clients.
#
# Three routes, each integrated with its own Lambda:
#   $connect    → ws_connect    — register META row in connections table
#   $disconnect → ws_disconnect — clean up META + GAME# rows
#   $default    → ws_default    — handle client {subscribe,unsubscribe} actions
#
# The stream-processor Lambda (commit 3) consumes DynamoDB Streams from the
# games table, queries the connections table by-game GSI to find subscribed
# connections, and uses the API Gateway Management API (PostToConnection)
# against this WebSocket API to push payloads to clients.
#
# WebSocket traffic does NOT flow through CloudFront/WAF in v1 — see ADR 011
# for the threat-model justification (data exposure is identical to the
# already-protected HTTP API). CloudFront fronting via path-based behavior
# is a future polish item.
###############################################################################

resource "aws_apigatewayv2_api" "ws" {
  name                       = "${local.name_prefix}-ws"
  protocol_type              = "WEBSOCKET"
  route_selection_expression = "$request.body.action"
}

resource "aws_cloudwatch_log_group" "ws_access" {
  name              = "/aws/apigateway/${local.name_prefix}-ws"
  retention_in_days = 14
}

resource "aws_apigatewayv2_stage" "ws" {
  api_id      = aws_apigatewayv2_api.ws.id
  name        = "production"
  auto_deploy = true

  default_route_settings {
    throttling_burst_limit   = 100
    throttling_rate_limit    = 100
    detailed_metrics_enabled = true
  }

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.ws_access.arn
    format = jsonencode({
      requestId      = "$context.requestId"
      requestTime    = "$context.requestTime"
      routeKey       = "$context.routeKey"
      status         = "$context.status"
      connectionId   = "$context.connectionId"
      eventType      = "$context.eventType"
      messageId      = "$context.messageId"
      sourceIp       = "$context.identity.sourceIp"
      integrationErr = "$context.integrationErrorMessage"
    })
  }
}

###############################################################################
# Integrations + routes (one of each per Lambda)
###############################################################################

resource "aws_apigatewayv2_integration" "ws_connect" {
  api_id                    = aws_apigatewayv2_api.ws.id
  integration_type          = "AWS_PROXY"
  integration_method        = "POST"
  integration_uri           = module.lambda_ws_connect.invoke_arn
  content_handling_strategy = "CONVERT_TO_TEXT"
  passthrough_behavior      = "WHEN_NO_MATCH"
}

resource "aws_apigatewayv2_route" "ws_connect" {
  api_id    = aws_apigatewayv2_api.ws.id
  route_key = "$connect"
  target    = "integrations/${aws_apigatewayv2_integration.ws_connect.id}"
}

resource "aws_apigatewayv2_integration" "ws_disconnect" {
  api_id                    = aws_apigatewayv2_api.ws.id
  integration_type          = "AWS_PROXY"
  integration_method        = "POST"
  integration_uri           = module.lambda_ws_disconnect.invoke_arn
  content_handling_strategy = "CONVERT_TO_TEXT"
  passthrough_behavior      = "WHEN_NO_MATCH"
}

resource "aws_apigatewayv2_route" "ws_disconnect" {
  api_id    = aws_apigatewayv2_api.ws.id
  route_key = "$disconnect"
  target    = "integrations/${aws_apigatewayv2_integration.ws_disconnect.id}"
}

resource "aws_apigatewayv2_integration" "ws_default" {
  api_id                    = aws_apigatewayv2_api.ws.id
  integration_type          = "AWS_PROXY"
  integration_method        = "POST"
  integration_uri           = module.lambda_ws_default.invoke_arn
  content_handling_strategy = "CONVERT_TO_TEXT"
  passthrough_behavior      = "WHEN_NO_MATCH"
}

resource "aws_apigatewayv2_route" "ws_default" {
  api_id    = aws_apigatewayv2_api.ws.id
  route_key = "$default"
  target    = "integrations/${aws_apigatewayv2_integration.ws_default.id}"
}

###############################################################################
# Lambda invoke permissions for API Gateway
###############################################################################

resource "aws_lambda_permission" "ws_connect_invoke" {
  statement_id  = "AllowApiGatewayInvokeWsConnect"
  action        = "lambda:InvokeFunction"
  function_name = module.lambda_ws_connect.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.ws.execution_arn}/*/*"
}

resource "aws_lambda_permission" "ws_disconnect_invoke" {
  statement_id  = "AllowApiGatewayInvokeWsDisconnect"
  action        = "lambda:InvokeFunction"
  function_name = module.lambda_ws_disconnect.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.ws.execution_arn}/*/*"
}

resource "aws_lambda_permission" "ws_default_invoke" {
  statement_id  = "AllowApiGatewayInvokeWsDefault"
  action        = "lambda:InvokeFunction"
  function_name = module.lambda_ws_default.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.ws.execution_arn}/*/*"
}
