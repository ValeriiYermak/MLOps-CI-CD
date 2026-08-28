# Дізнаємось поточний AWS Account ID та регіон —
# знадобиться для побудови ARN у IAM-політиках та Step Function definition.
data "aws_caller_identity" "current" {}

data "aws_region" "current" {}

# --- IAM Assume Role Policy для Lambda ---
# Цей документ каже: "сервісу lambda.amazonaws.com дозволено
# 'приміряти' (assume) цю роль" — це стандартний, обов'язковий
# перший крок для будь-якої IAM-ролі, яку використовує AWS-сервіс.
data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

# --- IAM Assume Role Policy для Step Function ---
# Той самий принцип, але для сервісу states.amazonaws.com
# (це внутрішня назва AWS-сервісу Step Functions).
data "aws_iam_policy_document" "states_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
  }
}