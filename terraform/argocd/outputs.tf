output "argocd_namespace" {
  description = "Namespace, у якому розгорнуто Argo CD"
  value       = helm_release.argocd.namespace
}

output "argocd_release_name" {
  description = "Назва Helm-релізу Argo CD"
  value       = helm_release.argocd.name
}

output "argocd_release_status" {
  description = "Статус Helm-релізу після apply"
  value       = helm_release.argocd.status
}

output "get_pods_command" {
  description = "Команда для перевірки подів Argo CD"
  value       = "kubectl get pods -n ${var.argocd_namespace}"
}

output "port_forward_ui_command" {
  description = "Команда для доступу до Argo CD UI через port-forward"
  value       = "kubectl port-forward svc/argocd-server -n ${var.argocd_namespace} 8080:443"
}

output "get_initial_admin_password_command" {
  description = "Команда для отримання початкового пароля адміністратора Argo CD"
  value       = "kubectl -n ${var.argocd_namespace} get secret argocd-initial-admin-secret -o jsonpath=\"{.data.password}\" | base64 -d"
}