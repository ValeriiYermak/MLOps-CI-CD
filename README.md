# MLOps Final Project

MLOps-платформа: MLflow Model Registry, promotion workflow (Staging → Production),
Blue-Green deployment, моніторинг (Prometheus + Grafana + Loki), security baseline.

## Режим розгортання: локальний fallback

Проєкт розгортається локально через **kind** (Kubernetes in Docker), а не на AWS EKS.
Причина: обмеження AWS-акаунту (доступний лише інстанс-тип t3.micro, недостатньо
ресурсів для повного стеку — MLflow, staging+production, моніторинг одночасно).
Використано офіційно узгоджений з ментором сценарій "Локальний fallback для
студентів без AWS-доступу":

| AWS-компонент | Локальна заміна |
|---|---|
| Amazon EKS | kind |
| Amazon ECR | локальний Docker registry (`registry:2`) |
| Amazon S3 | MinIO |
| AWS Step Functions | Argo Workflows / GitLab CI |
| AWS IAM | Kubernetes ServiceAccounts + RBAC |

## Залежності

| Інструмент | Версія (перевірена) |
|---|---|
| Docker | Docker Desktop, Windows |
| kind | 0.33.0 |
| kubectl | v1.36.1 |
| helm | v4.2.4 |
| terraform | v1.15.8 (CLI ≥ 1.5 вимога виконана) |

## Структура репозиторію

```
Final_Project/
├── kind/                    # конфігурація kind-кластера
├── k8s/namespaces/          # bootstrap-манифест namespaces
├── terraform/
│   ├── argocd/               # Terraform-модуль: ArgoCD через helm_release
│   ├── mlflow/                # (заплановано)
│   └── monitoring/            # (заплановано)
├── argocd/applications/      # ArgoCD Application-манифести (джерело правди для деплоїв)
├── training/                 # тренування моделі, реєстрація в MLflow Registry
├── inference/                 # (заплановано) FastAPI inference-сервіс
├── workflows/                 # заміна AWS Step Functions (Argo Workflows/CI)
├── rbac/                      # (заплановано) RBAC-ролі
└── docs/                      # додаткова документація
```

## Bootstrap-послідовність (з нуля)

Bootstrap виконується в кілька явних фаз. Перші дві фази — вручну (`kubectl apply`),
оскільки на цьому етапі ArgoCD ще не існує і не може керувати ресурсами через Git.
Усі наступні деплої — виключно через ArgoCD.

### Фаза 1 — Локальний Kubernetes-кластер

```powershell
docker run -d --restart=always -p 127.0.0.1:5001:5000 --name kind-registry registry:2
kind create cluster --config .\kind\kind-config.yaml
docker network connect kind kind-registry
kubectl cluster-info --context kind-mlops-final
```

Перевірка: `kubectl cluster-info` повертає адресу control-plane без помилок.

### Фаза 2 — Namespaces (bootstrap, вручну)

```powershell
kubectl apply -f .\k8s\namespaces\namespaces.yaml
kubectl get namespaces
```

Перевірка: `staging`, `production`, `mlops-system`, `monitoring` у статусі `Active`.

Призначення namespace:
- `staging` — тестове середовище для нових версій моделі
- `production` — production-трафік, Blue-Green деплой inference-сервісу
- `mlops-system` — інфраструктурні компоненти (MLflow, MinIO, PostgreSQL)
- `monitoring` — Prometheus, Grafana, Loki

### Фаза 3 — ArgoCD (Terraform)

```powershell
cd terraform\argocd
terraform init
terraform apply
```

Перевірка:
```powershell
kubectl get pods -n infra-tools
```
Усі поди мають бути `Running` (`argocd-server`, `argocd-repo-server`,
`argocd-application-controller`, `argocd-applicationset-controller`, `argocd-redis`).

Доступ до UI:
```powershell
kubectl port-forward svc/argocd-server -n infra-tools 8080:443
kubectl -n infra-tools get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d
```

### Фаза 4 і далі — усі інші компоненти через ArgoCD

Починаючи з цього моменту, жодних ручних `kubectl apply`/`helm install` — усі сервіси
(MLflow, MinIO, PostgreSQL, Prometheus, Grafana, Loki, inference) деплояться як
ArgoCD Application з `argocd/applications/`. *(розділ доповнюється по мірі виконання)*

---
*Документ доповнюється по ходу виконання проєкту.*