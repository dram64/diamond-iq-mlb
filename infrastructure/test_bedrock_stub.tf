###############################################################################
# Sub-phase 9A only — Bedrock IAM + invocation smoke test.
#
# This file (and the matching `functions/test_bedrock/` Lambda source) is
# temporary. It exists to prove that:
#   - the Anthropic-form-gated Bedrock account can invoke Claude
#   - a Lambda execution role with `bedrock:InvokeModel` scoped to the
#     inference-profile ARN and the underlying foundation-model ARNs
#     can call Claude through the cross-region routing
#
# After 9A verification we remove both this file and `functions/test_bedrock/`.
###############################################################################

locals {
  bedrock_inference_profile_id = "us.anthropic.claude-sonnet-4-6"

  bedrock_inference_profile_arn = "arn:aws:bedrock:${var.aws_region}:${local.account_id}:inference-profile/${local.bedrock_inference_profile_id}"

  # Cross-region inference routes to foundation models in three regions.
  # InvokeModel must be allowed against both the profile AND the underlying
  # foundation-model ARNs in every region the profile may route to.
  bedrock_foundation_model_arns = [
    "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-sonnet-4-6",
    "arn:aws:bedrock:us-east-2::foundation-model/anthropic.claude-sonnet-4-6",
    "arn:aws:bedrock:us-west-2::foundation-model/anthropic.claude-sonnet-4-6",
  ]
}

data "aws_iam_policy_document" "test_bedrock_invoke" {
  statement {
    sid     = "BedrockInvokeClaudeSonnet46"
    effect  = "Allow"
    actions = ["bedrock:InvokeModel"]
    resources = concat(
      [local.bedrock_inference_profile_arn],
      local.bedrock_foundation_model_arns,
    )
  }
}

module "lambda_test_bedrock" {
  source = "./modules/lambda"

  function_name = "${local.name_prefix}-test-bedrock"
  handler       = "handler.lambda_handler"
  source_dir    = "${path.module}/../functions/test_bedrock"
  shared_dir    = local.shared_dir

  environment_variables = {
    BEDROCK_MODEL_ID = local.bedrock_inference_profile_id
  }

  timeout             = 30
  memory_size         = 256
  iam_policy_document = data.aws_iam_policy_document.test_bedrock_invoke.json
}

output "test_bedrock_function_name" {
  description = "Name of the Bedrock smoke-test Lambda (temporary, 9A only)."
  value       = module.lambda_test_bedrock.function_name
}
