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

variable "cluster_name" {
  description = "Назва вже існуючого EKS-кластера, куди розгортаємо Argo CD"
  type        = string
  default     = "mlops-eks-cluster"
}

variable "argocd_namespace" {
  description = "Namespace, у якому буде розгорнуто Argo CD"
  type        = string
  default     = "infra-tools"
}

variable "argocd_chart_version" {
  description = "Версія офіційного Helm-чарту Argo CD"
  type        = string
  default     = "7.7.11"
}