output "state_machine_arn" {
  description = "ARN Step Function state machine — використовується в GitLab CI та для ручного запуску"
  value       = aws_sfn_state_machine.train_pipeline.arn
}

output "validate_lambda_arn" {
  description = "ARN Lambda-функції validate"
  value       = aws_lambda_function.validate.arn
}

output "log_metrics_lambda_arn" {
  description = "ARN Lambda-функції log_metrics"
  value       = aws_lambda_function.log_metrics.arn
}

output "start_execution_command" {
  description = "Готова команда для ручного запуску Step Function через AWS CLI"
  value       = "aws stepfunctions start-execution --state-machine-arn ${aws_sfn_state_machine.train_pipeline.arn} --name manual-run-$(date +%s) --input '{\"source\": \"manual\"}'"
}