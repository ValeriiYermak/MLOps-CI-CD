variable "aws_region" {
  description = "AWS регіон"
  type        = string
  default     = "us-east-1"
}

variable "aws_profile" {
  description = "AWS CLI профіль для автентифікації"
  type        = string
  default     = "goit-terraform"
}

variable "project_name" {
  description = "Назва проєкту, використовується для іменування ресурсів"
  type        = string
  default     = "mlops-train-automation"
}

variable "lambda_runtime" {
  description = "Версія Python-рантайму для Lambda-функцій"
  type        = string
  default     = "python3.12"
}

variable "lambda_timeout" {
  description = "Таймаут виконання Lambda-функції (секунди)"
  type        = number
  default     = 30
}

variable "lambda_memory_size" {
  description = "Обсяг пам'яті для Lambda-функції (MB)"
  type        = number
  default     = 128
}