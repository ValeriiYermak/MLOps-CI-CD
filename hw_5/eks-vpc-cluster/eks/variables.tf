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
  description = "Назва проєкту, для тегування ресурсів"
  type        = string
  default     = "mlops-eks"
}

variable "cluster_name" {
  description = "Назва EKS-кластера"
  type        = string
  default     = "mlops-eks-cluster"
}

variable "cluster_version" {
  description = "Версія Kubernetes для EKS-кластера"
  type        = string
  default     = "1.30"
}

variable "cpu_node_instance_types" {
  description = "Типи інстансів для cpu-nodes"
  type        = list(string)
  default     = ["t3.micro"]
}

variable "cpu_node_desired_size" {
  description = "Бажана кількість нод у cpu-nodes"
  type        = number
  default     = 2
}

variable "cpu_node_min_size" {
  description = "Мінімальна кількість нод у cpu-nodes"
  type        = number
  default     = 1
}

variable "cpu_node_max_size" {
  description = "Максимальна кількість нод у cpu-nodes"
  type        = number
  default     = 3
}

variable "gpu_node_instance_types" {
  description = "Типи інстансів для gpu-nodes (за замовчуванням не справжній GPU, щоб не платити зайве)"
  type        = list(string)
  default     = ["t3.micro"]
}

variable "gpu_node_desired_size" {
  description = "Бажана кількість нод у gpu-nodes"
  type        = number
  default     = 1
}

variable "gpu_node_min_size" {
  description = "Мінімальна кількість нод у gpu-nodes"
  type        = number
  default     = 0
}

variable "gpu_node_max_size" {
  description = "Максимальна кількість нод у gpu-nodes"
  type        = number
  default     = 2
}