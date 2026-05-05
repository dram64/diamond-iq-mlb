###############################################################################
# Reusable Lambda module.
#
# Builds the deploy zip directly from source files using archive_file's
# dynamic source blocks. Function files land at the zip root; shared/*.py
# are vendored under shared/ inside the same zip.
#
# Pure plan-time evaluation — no staging directory, no null_resource, no
# bash provisioners. Works identically on a fresh GitHub Actions runner and
# on a developer machine.
###############################################################################

terraform {
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
}

locals {
  zip_path = "${path.module}/.build/${var.function_name}.zip"

  # Only Python files get vendored. Anything else (caches, .pytest_cache,
  # __pycache__, requirements.txt left empty) stays out of the zip.
  function_files = fileset(var.source_dir, "**/*.py")
  shared_files   = fileset(var.shared_dir, "**/*.py")
}

data "archive_file" "package" {
  type        = "zip"
  output_path = local.zip_path

  # Function source — written at the zip root, so the handler entry-point
  # path matches `var.handler` (e.g. "handler.lambda_handler" → handler.py
  # at the root).
  dynamic "source" {
    for_each = local.function_files
    content {
      content  = file("${var.source_dir}/${source.value}")
      filename = source.value
    }
  }

  # Shared package — vendored under shared/ so `from shared.dynamodb import ...`
  # resolves the same way it does in tests via the project's pythonpath.
  dynamic "source" {
    for_each = local.shared_files
    content {
      content  = file("${var.shared_dir}/${source.value}")
      filename = "shared/${source.value}"
    }
  }
}

###############################################################################
# IAM
###############################################################################

data "aws_iam_policy_document" "assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "function" {
  name               = "${var.function_name}-role"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

# Caller-supplied policy (DynamoDB scoped to the games table, etc.).
resource "aws_iam_role_policy" "function" {
  name   = "${var.function_name}-policy"
  role   = aws_iam_role.function.id
  policy = var.iam_policy_document
}

# Standard Lambda → CloudWatch Logs permissions.
resource "aws_iam_role_policy_attachment" "basic_execution" {
  role       = aws_iam_role.function.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

###############################################################################
# Log group
###############################################################################

resource "aws_cloudwatch_log_group" "function" {
  name              = "/aws/lambda/${var.function_name}"
  retention_in_days = var.log_retention_days
}

###############################################################################
# Function
###############################################################################

resource "aws_lambda_function" "function" {
  function_name                  = var.function_name
  role                           = aws_iam_role.function.arn
  handler                        = var.handler
  runtime                        = "python3.12"
  filename                       = data.archive_file.package.output_path
  source_code_hash               = data.archive_file.package.output_base64sha256
  timeout                        = var.timeout
  memory_size                    = var.memory_size
  reserved_concurrent_executions = var.reserved_concurrent_executions

  environment {
    variables = var.environment_variables
  }

  # Make sure the log group exists (and is set to our retention) before the
  # function — otherwise Lambda creates a default group with infinite retention.
  depends_on = [aws_cloudwatch_log_group.function]
}
