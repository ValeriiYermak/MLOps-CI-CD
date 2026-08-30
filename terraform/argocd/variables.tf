variable "kubeconfig_path" {
  description = "Шлях до kubeconfig файлу"
  type        = string
  default     = "~/.kube/config"
}

variable "kube_context" {
  description = "Kubernetes context для kind-кластера"
  type        = string
  default     = "kind-mlops-final"
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
