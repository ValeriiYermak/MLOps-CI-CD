provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile
}

# ============================================================
# IAM-роль для Lambda-функцій
# ============================================================

resource "aws_iam_role" "lambda_role" {
  name               = "${var.project_name}-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

# Базова, керована AWS політика — дозволяє Lambda писати логи
# в CloudWatch Logs. Без цього функція технічно виконається,
# але ти не побачиш print()-виводи ніде.
resource "aws_iam_role_policy_attachment" "lambda_logs" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# ============================================================
# Lambda-функції
# ============================================================

resource "aws_lambda_function" "validate" {
  function_name = "${var.project_name}-validate"
  role          = aws_iam_role.lambda_role.arn
  handler       = "validate.handler"
  runtime       = var.lambda_runtime
  timeout       = var.lambda_timeout
  memory_size   = var.lambda_memory_size

  filename         = "${path.module}/lambda/validate.zip"
  source_code_hash = filebase64sha256("${path.module}/lambda/validate.zip")
}

resource "aws_lambda_function" "log_metrics" {
  function_name = "${var.project_name}-log-metrics"
  role          = aws_iam_role.lambda_role.arn
  handler       = "log_metrics.handler"
  runtime       = var.lambda_runtime
  timeout       = var.lambda_timeout
  memory_size   = var.lambda_memory_size

  filename         = "${path.module}/lambda/log_metrics.zip"
  source_code_hash = filebase64sha256("${path.module}/lambda/log_metrics.zip")
}

# ============================================================
# IAM-роль для Step Function
# ============================================================

resource "aws_iam_role" "step_function_role" {
  name               = "${var.project_name}-step-function-role"
  assume_role_policy = data.aws_iam_policy_document.states_assume_role.json
}

# Власноруч написана політика — на відміну від Lambda-ролі,
# тут немає готової AWS-політики "дозволити викликати ось ці
# дві конкретні функції", тому пишемо її самі.
data "aws_iam_policy_document" "step_function_lambda_invoke" {
  statement {
    effect  = "Allow"
    actions = ["lambda:InvokeFunction"]

    resources = [
      aws_lambda_function.validate.arn,
      aws_lambda_function.log_metrics.arn,
    ]
  }
}

resource "aws_iam_role_policy" "step_function_lambda_invoke" {
  name   = "${var.project_name}-invoke-lambda-policy"
  role   = aws_iam_role.step_function_role.id
  policy = data.aws_iam_policy_document.step_function_lambda_invoke.json
}

# ============================================================
# Step Function — validate → log_metrics
# ============================================================

resource "aws_sfn_state_machine" "train_pipeline" {
  name     = "${var.project_name}-pipeline"
  role_arn = aws_iam_role.step_function_role.arn

  definition = jsonencode({
    Comment = "Спрощений training pipeline: валідація даних, потім логування метрик"
    StartAt = "ValidateData"

    States = {
      ValidateData = {
        Type     = "Task"
        Resource = aws_lambda_function.validate.arn
        Next     = "LogMetrics"
      }

      LogMetrics = {
        Type     = "Task"
        Resource = aws_lambda_function.log_metrics.arn
        End      = true
      }
    }
  })
}

