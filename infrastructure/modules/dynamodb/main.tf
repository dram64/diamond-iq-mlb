###############################################################################
# Single-table design for game data.
#
# PK pattern: "GAME#<yyyy-mm-dd>"
# SK pattern: "GAME#<game_pk>"
# TTL attribute: "ttl" (Unix epoch seconds, ~7 days from write)
###############################################################################

resource "aws_dynamodb_table" "games" {
  name         = var.table_name
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

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }

  # Stream feeds the real-time WebSocket pipeline. NEW_AND_OLD_IMAGES is
  # required so the stream-processor Lambda can diff old vs new and only
  # push meaningful changes (score, linescore, status) to subscribed
  # clients — most ingest writes are no-op TTL refreshes.
  stream_enabled   = true
  stream_view_type = "NEW_AND_OLD_IMAGES"
}
