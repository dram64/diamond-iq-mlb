###############################################################################
# GitHub Actions OIDC trust + deploy role.
#
# Lets workflows in github.com/<github_repo> assume an AWS role without any
# long-lived AWS credentials in the repo. The deploy role's permissions are
# scoped to project resources only via ARN patterns.
###############################################################################

resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

###############################################################################
# Trust policy
###############################################################################

data "aws_iam_policy_document" "trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    # Any branch / tag / PR from this repo can assume the role. Tighten in a
    # later phase (e.g. only main + tags).
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repo}:*"]
    }
  }
}

resource "aws_iam_role" "deploy" {
  name               = var.role_name
  assume_role_policy = data.aws_iam_policy_document.trust.json
}

###############################################################################
# Deploy permissions, scoped to project resource ARN patterns
###############################################################################

data "aws_iam_policy_document" "deploy" {
  # Lambda — manage just the project's two functions.
  statement {
    sid    = "LambdaManageProjectFunctions"
    effect = "Allow"
    actions = [
      "lambda:GetFunction",
      "lambda:GetFunctionConfiguration",
      "lambda:GetFunctionCodeSigningConfig",
      "lambda:ListVersionsByFunction",
      "lambda:UpdateFunctionCode",
      "lambda:UpdateFunctionConfiguration",
      "lambda:CreateFunction",
      "lambda:DeleteFunction",
      "lambda:TagResource",
      "lambda:UntagResource",
      "lambda:ListTags",
      "lambda:AddPermission",
      "lambda:RemovePermission",
      "lambda:GetPolicy",
      # Per-function concurrency reservations (ADR 013). These are
      # separate IAM actions from UpdateFunctionConfiguration even
      # though they affect the same resource — same pattern as
      # lambda:TagResource on event-source-mapping ARNs.
      "lambda:GetFunctionConcurrency",
      "lambda:PutFunctionConcurrency",
      "lambda:DeleteFunctionConcurrency",
    ]
    resources = ["arn:aws:lambda:${var.aws_region}:${var.account_id}:function:${var.name_prefix}-*"]
  }

  # Lambda event source mappings (used by the stream-processor → DynamoDB
  # Streams trigger). These actions don't accept resource-level scoping
  # at the mapping ARN; effectively scoped to project Lambdas via PassRole
  # and the function-name perms above. Tag actions are required because
  # the AWS provider applies default_tags to mappings, and the
  # function-level TagResource grant doesn't cover the
  # arn:...:event-source-mapping:* ARN class.
  statement {
    sid    = "LambdaManageEventSourceMappings"
    effect = "Allow"
    actions = [
      "lambda:CreateEventSourceMapping",
      "lambda:GetEventSourceMapping",
      "lambda:UpdateEventSourceMapping",
      "lambda:DeleteEventSourceMapping",
      "lambda:ListEventSourceMappings",
      "lambda:TagResource",
      "lambda:UntagResource",
      "lambda:ListTags",
    ]
    resources = ["*"]
  }

  # State bucket — full S3 access on the bucket and its objects only.
  statement {
    sid    = "S3StateBucket"
    effect = "Allow"
    actions = [
      "s3:ListBucket",
      "s3:GetBucketVersioning",
      "s3:GetObject",
      "s3:GetObjectVersion",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:DeleteObjectVersion",
    ]
    resources = [
      "arn:aws:s3:::${var.state_bucket_name}",
      "arn:aws:s3:::${var.state_bucket_name}/*",
    ]
  }

  # Lock table — full DynamoDB access on the lock table only.
  statement {
    sid    = "DynamoDBLockTable"
    effect = "Allow"
    actions = [
      "dynamodb:DescribeTable",
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:DeleteItem",
    ]
    resources = ["arn:aws:dynamodb:${var.aws_region}:${var.account_id}:table/${var.lock_table_name}"]
  }

  # Project DynamoDB tables — manage shape, indexes, streams, TTL, backups.
  # Scope is broadened from `${name_prefix}-games` to every project table
  # because the Option 4 streaming work introduces `${name_prefix}-connections`
  # and any future project tables should also be deployable from here.
  # Stream and index sub-resource ARNs are listed explicitly because IAM
  # treats them as separate resources from the table itself.
  statement {
    sid    = "DynamoDBProjectTablesManage"
    effect = "Allow"
    actions = [
      "dynamodb:DescribeTable",
      "dynamodb:DescribeContinuousBackups",
      "dynamodb:DescribeTimeToLive",
      "dynamodb:ListTagsOfResource",
      "dynamodb:UpdateTable",
      "dynamodb:UpdateContinuousBackups",
      "dynamodb:UpdateTimeToLive",
      "dynamodb:CreateTable",
      "dynamodb:DeleteTable",
      "dynamodb:TagResource",
      "dynamodb:UntagResource",
      "dynamodb:DescribeStream",
      "dynamodb:ListStreams",
    ]
    resources = [
      "arn:aws:dynamodb:${var.aws_region}:${var.account_id}:table/${var.name_prefix}-*",
      "arn:aws:dynamodb:${var.aws_region}:${var.account_id}:table/${var.name_prefix}-*/index/*",
      "arn:aws:dynamodb:${var.aws_region}:${var.account_id}:table/${var.name_prefix}-*/stream/*",
    ]
  }

  # CloudWatch Logs — manage the project's log groups only.
  statement {
    sid    = "LogsManageProjectGroups"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:DeleteLogGroup",
      "logs:DescribeLogStreams",
      "logs:PutRetentionPolicy",
      "logs:DeleteRetentionPolicy",
      "logs:TagLogGroup",
      "logs:UntagLogGroup",
      "logs:ListTagsLogGroup",
      "logs:ListTagsForResource",
    ]
    resources = [
      "arn:aws:logs:${var.aws_region}:${var.account_id}:log-group:/aws/lambda/${var.name_prefix}-*",
      "arn:aws:logs:${var.aws_region}:${var.account_id}:log-group:/aws/lambda/${var.name_prefix}-*:*",
      "arn:aws:logs:${var.aws_region}:${var.account_id}:log-group:/aws/apigateway/${var.name_prefix}-*",
      "arn:aws:logs:${var.aws_region}:${var.account_id}:log-group:/aws/apigateway/${var.name_prefix}-*:*",
      # WAF requires log groups prefixed with "aws-waf-logs-".
      "arn:aws:logs:${var.aws_region}:${var.account_id}:log-group:aws-waf-logs-${var.name_prefix}",
      "arn:aws:logs:${var.aws_region}:${var.account_id}:log-group:aws-waf-logs-${var.name_prefix}:*",
    ]
  }

  # logs:DescribeLogGroups requires a wildcard resource because the API does
  # not accept resource-level scoping for it. Filtering happens by name in
  # Terraform's refresh logic.
  statement {
    sid       = "LogsDescribeAll"
    effect    = "Allow"
    actions   = ["logs:DescribeLogGroups"]
    resources = ["*"]
  }

  # wafv2:PutLoggingConfiguration internally invokes log-delivery actions and
  # resource-policy writes on the calling principal's behalf to wire WAF
  # (source) to a CloudWatch log group (destination). These actions don't
  # support resource-level ARN scoping in IAM, so wildcard is required —
  # same constraint as logs:DescribeLogGroups above.
  statement {
    sid    = "LogsLogDeliveryForWAF"
    effect = "Allow"
    actions = [
      "logs:CreateLogDelivery",
      "logs:GetLogDelivery",
      "logs:UpdateLogDelivery",
      "logs:DeleteLogDelivery",
      "logs:ListLogDeliveries",
      "logs:PutResourcePolicy",
      "logs:DescribeResourcePolicies",
    ]
    resources = ["*"]
  }

  # WAFv2 logging requires the AWSServiceRoleForWAFV2Logging service-linked
  # role. AWS creates it on first PutLoggingConfiguration call against an
  # account that doesn't already have it. The deploy role needs permission
  # to allow that creation. The condition pins the action to wafv2's SLR
  # only, so this grant can't be used to mint other service roles.
  statement {
    sid       = "CreateWAFLogsServiceLinkedRole"
    effect    = "Allow"
    actions   = ["iam:CreateServiceLinkedRole"]
    resources = ["arn:aws:iam::*:role/aws-service-role/wafv2.amazonaws.com/*"]
    condition {
      test     = "StringLike"
      variable = "iam:AWSServiceName"
      values   = ["wafv2.amazonaws.com"]
    }
  }

  # PassRole — only the Lambda execution roles, only to lambda.amazonaws.com.
  statement {
    sid       = "IamPassRoleToLambda"
    effect    = "Allow"
    actions   = ["iam:PassRole"]
    resources = ["arn:aws:iam::${var.account_id}:role/${var.name_prefix}-*"]
    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["lambda.amazonaws.com"]
    }
  }

  # IAM — manage the project's roles and policies only.
  statement {
    sid    = "IamManageProjectRoles"
    effect = "Allow"
    actions = [
      "iam:GetRole",
      "iam:GetRolePolicy",
      "iam:CreateRole",
      "iam:DeleteRole",
      "iam:PutRolePolicy",
      "iam:DeleteRolePolicy",
      "iam:AttachRolePolicy",
      "iam:DetachRolePolicy",
      "iam:ListAttachedRolePolicies",
      "iam:ListRolePolicies",
      "iam:UpdateAssumeRolePolicy",
      "iam:TagRole",
      "iam:UntagRole",
    ]
    resources = ["arn:aws:iam::${var.account_id}:role/${var.name_prefix}-*"]
  }

  # OIDC provider — manage the GitHub Actions provider that this very role's
  # trust policy depends on. Terraform refresh needs to read it on every plan.
  statement {
    sid    = "IamManageGitHubOIDCProvider"
    effect = "Allow"
    actions = [
      "iam:GetOpenIDConnectProvider",
      "iam:CreateOpenIDConnectProvider",
      "iam:DeleteOpenIDConnectProvider",
      "iam:UpdateOpenIDConnectProviderThumbprint",
      "iam:AddClientIDToOpenIDConnectProvider",
      "iam:RemoveClientIDFromOpenIDConnectProvider",
      "iam:TagOpenIDConnectProvider",
      "iam:UntagOpenIDConnectProvider",
      "iam:ListOpenIDConnectProviderTags",
    ]
    resources = [
      "arn:aws:iam::${var.account_id}:oidc-provider/token.actions.githubusercontent.com",
    ]
  }

  # API Gateway — manage the project's APIs and sub-resources, plus the
  # account-level CloudWatch Logs role configuration that v2 WebSocket
  # stages require for access logging.
  statement {
    sid    = "ApiGatewayManage"
    effect = "Allow"
    actions = [
      "apigateway:GET",
      "apigateway:POST",
      "apigateway:PUT",
      "apigateway:PATCH",
      "apigateway:DELETE",
      "apigateway:TagResource",
      "apigateway:UntagResource",
    ]
    resources = [
      "arn:aws:apigateway:${var.aws_region}::/apis",
      "arn:aws:apigateway:${var.aws_region}::/apis/*",
      "arn:aws:apigateway:${var.aws_region}::/tags/*",
      "arn:aws:apigateway:${var.aws_region}::/account",
    ]
  }

  # Allow the deploy role to PassRole the API Gateway → CloudWatch Logs
  # role to apigateway.amazonaws.com. Scoped tightly: only the project's
  # apigateway-cloudwatch-logs role, only when passed to API Gateway.
  statement {
    sid       = "IamPassRoleToApiGateway"
    effect    = "Allow"
    actions   = ["iam:PassRole"]
    resources = ["arn:aws:iam::${var.account_id}:role/${var.name_prefix}-apigateway-cloudwatch-logs"]
    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["apigateway.amazonaws.com"]
    }
  }

  # EventBridge — manage the project's rules only.
  statement {
    sid    = "EventBridgeManageProjectRules"
    effect = "Allow"
    actions = [
      "events:DescribeRule",
      "events:ListTargetsByRule",
      "events:ListTagsForResource",
      "events:PutRule",
      "events:DeleteRule",
      "events:PutTargets",
      "events:RemoveTargets",
      "events:EnableRule",
      "events:DisableRule",
      "events:TagResource",
      "events:UntagResource",
    ]
    resources = ["arn:aws:events:${var.aws_region}:${var.account_id}:rule/${var.name_prefix}-*"]
  }

  # CloudWatch — read access (metrics/dashboards) on the project's namespace.
  statement {
    sid    = "CloudWatchRead"
    effect = "Allow"
    actions = [
      "cloudwatch:DescribeAlarms",
      "cloudwatch:GetMetricData",
      "cloudwatch:GetMetricStatistics",
      "cloudwatch:ListMetrics",
    ]
    resources = ["*"]
  }

  # CloudWatch alarms — manage the project's alarms only. Alarm ARN scoping
  # IS supported on PutMetricAlarm/DeleteAlarms/Tag* (unlike PutMetricData,
  # which is namespace-scoped on the Lambda's role).
  statement {
    sid    = "CloudWatchAlarmsManageProject"
    effect = "Allow"
    actions = [
      "cloudwatch:PutMetricAlarm",
      "cloudwatch:DeleteAlarms",
      "cloudwatch:TagResource",
      "cloudwatch:UntagResource",
      "cloudwatch:ListTagsForResource",
    ]
    resources = [
      "arn:aws:cloudwatch:${var.aws_region}:${var.account_id}:alarm:${var.name_prefix}-*",
    ]
  }

  # SNS — manage the project's topics and their subscriptions only.
  statement {
    sid    = "SnsManageProjectTopics"
    effect = "Allow"
    actions = [
      "sns:CreateTopic",
      "sns:DeleteTopic",
      "sns:GetTopicAttributes",
      "sns:SetTopicAttributes",
      "sns:Subscribe",
      "sns:Unsubscribe",
      "sns:GetSubscriptionAttributes",
      "sns:ListSubscriptionsByTopic",
      "sns:ListTagsForResource",
      "sns:TagResource",
      "sns:UntagResource",
    ]
    resources = [
      "arn:aws:sns:${var.aws_region}:${var.account_id}:${var.name_prefix}-*",
    ]
  }

  # sns:ListTopics has no resource-level ARN scoping (parallels
  # logs:DescribeLogGroups). Filtering happens by name in Terraform's
  # refresh logic.
  statement {
    sid       = "SnsListAll"
    effect    = "Allow"
    actions   = ["sns:ListTopics"]
    resources = ["*"]
  }

  # SQS — manage the project's queues only. The stream-processor DLQ
  # (ADR 013) is the first project queue; future queues land here too.
  statement {
    sid    = "SqsManageProjectQueues"
    effect = "Allow"
    actions = [
      "sqs:CreateQueue",
      "sqs:DeleteQueue",
      "sqs:GetQueueAttributes",
      "sqs:GetQueueUrl",
      "sqs:SetQueueAttributes",
      "sqs:TagQueue",
      "sqs:UntagQueue",
      "sqs:ListQueueTags",
    ]
    resources = ["arn:aws:sqs:${var.aws_region}:${var.account_id}:${var.name_prefix}-*"]
  }

  # sqs:ListQueues has no resource-level scoping — parallels
  # logs:DescribeLogGroups and sns:ListTopics.
  statement {
    sid       = "SqsListAll"
    effect    = "Allow"
    actions   = ["sqs:ListQueues"]
    resources = ["*"]
  }

  # WAFv2 — manage the project's Web ACL, IP set, and logging config only.
  # Web ACL ARNs include the name prefix; IP sets follow the same pattern.
  statement {
    sid    = "WAFv2ManageProjectAcl"
    effect = "Allow"
    actions = [
      "wafv2:CreateWebACL",
      "wafv2:DeleteWebACL",
      "wafv2:GetWebACL",
      "wafv2:UpdateWebACL",
      "wafv2:AssociateWebACL",
      "wafv2:DisassociateWebACL",
      "wafv2:GetWebACLForResource",
      "wafv2:GetLoggingConfiguration",
      "wafv2:PutLoggingConfiguration",
      "wafv2:DeleteLoggingConfiguration",
      "wafv2:CreateIPSet",
      "wafv2:DeleteIPSet",
      "wafv2:GetIPSet",
      "wafv2:UpdateIPSet",
      "wafv2:TagResource",
      "wafv2:UntagResource",
      "wafv2:ListTagsForResource",
    ]
    # Web ACL/IP-set ARNs follow:
    # arn:aws:wafv2:<region>:<account>:global/webacl/<name>/<id> (CLOUDFRONT scope)
    # arn:aws:wafv2:<region>:<account>:global/ipset/<name>/<id>
    resources = [
      "arn:aws:wafv2:${var.aws_region}:${var.account_id}:global/webacl/${var.name_prefix}-*/*",
      "arn:aws:wafv2:${var.aws_region}:${var.account_id}:global/ipset/${var.name_prefix}-*/*",
      "arn:aws:wafv2:${var.aws_region}:${var.account_id}:global/managedruleset/*/*",
    ]
  }

  # ListWebACLs/ListIPSets and the AWS-managed-rule-group queries don't
  # accept resource-level scoping. Required for Terraform refresh and for
  # the managed_rule_group_statement to resolve managed group versions.
  statement {
    sid    = "WAFv2ListAndDescribeManaged"
    effect = "Allow"
    actions = [
      "wafv2:ListWebACLs",
      "wafv2:ListIPSets",
      "wafv2:ListAvailableManagedRuleGroups",
      "wafv2:ListAvailableManagedRuleGroupVersions",
      "wafv2:DescribeManagedRuleGroup",
      "wafv2:CheckCapacity",
    ]
    resources = ["*"]
  }

  # CloudFront — manage the project's distribution and read AWS-managed
  # cache/origin-request policies. CloudFront is a global service; most
  # actions don't accept resource-level scoping in IAM.
  statement {
    sid    = "CloudFrontManage"
    effect = "Allow"
    actions = [
      "cloudfront:CreateDistribution",
      "cloudfront:UpdateDistribution",
      "cloudfront:DeleteDistribution",
      "cloudfront:GetDistribution",
      "cloudfront:GetDistributionConfig",
      "cloudfront:ListDistributions",
      "cloudfront:ListTagsForResource",
      "cloudfront:TagResource",
      "cloudfront:UntagResource",
      "cloudfront:GetCachePolicy",
      "cloudfront:GetOriginRequestPolicy",
      # Phase 8.5 PART 3 hotfix — terraform plan reads the frontend
      # distribution's OAC + response-headers-policy on every CI run;
      # missing Get* perms here caused PR #48 backend-deploy to fail.
      "cloudfront:GetOriginAccessControl",
      "cloudfront:GetResponseHeadersPolicy",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "deploy" {
  name   = "${var.role_name}-policy"
  role   = aws_iam_role.deploy.id
  policy = data.aws_iam_policy_document.deploy.json
}
