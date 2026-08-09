output "cluster_name" {
  description = "Назва EKS-кластера"
  value       = module.eks.cluster_name
}

output "cluster_endpoint" {
  description = "Endpoint API-сервера EKS-кластера"
  value       = module.eks.cluster_endpoint
}

output "node_groups" {
  description = "Інформація про створені node group-и"
  value       = module.eks.eks_managed_node_groups
}

output "update_kubeconfig_command" {
  description = "Готова команда для підключення kubectl до кластера"
  value       = "aws eks --region ${var.aws_region} --profile ${var.aws_profile} update-kubeconfig --name ${module.eks.cluster_name}"
}