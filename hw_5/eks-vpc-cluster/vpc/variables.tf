variable "aws_region" {
  description = "AWS регіон, в якому створюється інфраструктура"
  type        = string
  default     = "us-east-1"
}

variable "aws_profile" {
  description = "Назва AWS CLI профілю для автентифікації"
  type        = string
  default     = "goit-terraform"
}

variable "project_name" {
  description = "Назва проєкту, використовується для тегування ресурсів"
  type        = string
  default     = "mlops-eks"
}

variable "vpc_cidr" {
  description = "CIDR-блок для VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "azs" {
  description = "Список Availability Zones"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]
}

variable "public_subnets" {
  description = "CIDR-блоки для public subnet-ів"
  type        = list(string)
  default     = ["10.0.0.0/24", "10.0.1.0/24"]
}

variable "private_subnets" {
  description = "CIDR-блоки для private subnet-ів"
  type        = list(string)
  default     = ["10.0.10.0/24", "10.0.11.0/24"]
}