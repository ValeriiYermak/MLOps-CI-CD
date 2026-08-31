# MLOps Final Project

MLOps-платформа: MLflow Model Registry, promotion workflow (Staging → Production),
Blue-Green deployment, моніторинг (Prometheus + Grafana + Loki), security baseline.

Модель: Iris LogisticRegression (5 версій гіперпараметрів), тренування <1 хв.

## Режим розгортання: локальний fallback

Проєкт розгортається локально через **kind** (Kubernetes in Docker), а не на AWS EKS.
Причина: AWS-акаунт має доступ лише до інстанс-типу t3.micro — недостатньо ресурсів
для повного стеку (MLflow, staging+production, моніторинг одночасно). Використано
офіційно узгоджений з ментором сценарій "Локальний fallback для студентів без
AWS-доступу".

| AWS-компонент | Локальна заміна | Статус |
|---|---|---|
| Amazon EKS | kind | ✅ |
| Amazon ECR | локальний Docker registry (`registry:2`) | ✅ |
| Amazon S3 | MinIO (plain manifest, не Bitnami chart) | ✅ |
| AWS Step Functions | Argo Workflows / GitLab CI | заплановано |
| AWS IAM | Kubernetes ServiceAccounts + RBAC | заплановано |
| VPC, NAT Gateway, повні EKS Terraform-модулі | не потрібні | — |

## Архітектура

```
┌─────────────────────────── kind cluster "mlops-final" ───────────────────────────┐
│                                                                                     │
│  namespace: infra-tools          namespace: mlops-system                          │
│  ┌──────────────┐                ┌───────────┐  ┌────────────┐  ┌──────────────┐  │
│  │   ArgoCD     │──git-sync───▶  │   MinIO   │  │  Postgres  │  │    MLflow    │  │
│  │ (root-app +  │                │ (S3-заміна│  │ (backend   │◀─│  (Registry + │  │
│  │  Applications)│                │  для      │  │  store)    │  │   Tracking)  │  │
│  └──────┬───────┘                │  артефактів)│  └────────────┘  └──────┬───────┘  │
│         │                        └───────────┘                          │          │
│         │ manages                                                       │          │
│         ▼                                                               │          │
│  namespace: monitoring           namespace: staging / production        │          │
│  ┌───────────┐ ┌─────────┐       ┌──────────────────────────────┐      │          │
│  │ Prometheus│ │ Grafana │       │  inference (FastAPI, Blue-Green)│◀────┘          │
│  │ +Pushgw   │ │         │       │  завантажує модель з Registry  │                 │
│  └───────────┘ └─────────┘       └──────────────────────────────┘                  │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────┘
        ▲
        │ git push
┌───────┴────────┐
│  GitHub repo    │  ValeriiYermak/MLOps-CI-CD, гілка final-project
│  (джерело правди│  argocd/applications/*.yaml, k8s/*, terraform/*
│   для ArgoCD)   │
└─────────────────┘
```

## Залежності

| Інструмент | Версія (перевірена) |
|---|---|
| Docker Desktop (WSL2 backend) | — |
| kind | 0.33.0 |
| kubectl | v1.36.1 |
| helm | v4.2.4 |
| terraform | v1.15.8 (CLI ≥ 1.5 вимога виконана) |
| Python (для training-коду) | 3.12 (3.13 несумісний з pyarrow — немає готового wheel) |

## Структура репозиторію

```
Final_Project/
├── kind/                    # конфігурація kind-кластера
├── k8s/
│   ├── namespaces/          # bootstrap-манифест namespaces
│   ├── minio/                # plain Deployment+Service+Job (заміна Bitnami chart)
│   └── postgres/             # plain Deployment+Service (заміна Bitnami chart)
├── terraform/
│   ├── argocd/               # Terraform-модуль: ArgoCD через helm_release
│   ├── mlflow/                # (заплановано, поки через ArgoCD Application напряму)
│   └── monitoring/            # (заплановано)
├── argocd/
│   ├── root-app.yaml          # кореневий Application (app-of-apps)
│   └── applications/          # ArgoCD Application-манифести (джерело правди для деплоїв)
├── training/                 # тренування моделі, реєстрація в MLflow Registry
│   ├── train_and_push.py
│   ├── requirements.txt
│   └── .venv/                 # Python 3.12 venv (не в git)
├── inference/                 # (заплановано) FastAPI inference-сервіс
├── workflows/                 # заміна AWS Step Functions (Argo Workflows/CI)
├── rbac/                      # (заплановано) RBAC-ролі
└── docs/                      # додаткова документація
```

## Bootstrap-послідовність (з нуля)

Bootstrap виконується в кілька явних фаз. Перші дві — вручну (`kubectl apply`),
оскільки на цьому етапі ArgoCD ще не існує і не може керувати ресурсами через Git.
Третя (root-app) — теж одноразовий ручний виняток (курка-яйце: ArgoCD ще не
підключений до git). Усі наступні деплої — виключно через ArgoCD-sync з git.

### Фаза 1 — Локальний Kubernetes-кластер

```powershell
docker run -d --restart=always -p 127.0.0.1:5001:5000 --name kind-registry registry:2
kind create cluster --config .\kind\kind-config.yaml
docker network connect kind kind-registry
kubectl cluster-info --context kind-mlops-final
```

Перевірка: `kubectl cluster-info` повертає адресу control-plane без помилок.

**Важливо (WSL2/Docker Desktop):** якщо MLflow падає з `OOMKilled` (exit 137) навіть
при виставлених ресурсних лімітах — перевірте `%USERPROFILE%\.wslconfig`. За
замовчуванням WSL2 може мати занижений ліміт пам'яті. Виправлення:

```
[wsl2]
memory=8GB
processors=4
```

Після редагування — обов'язково `wsl --shutdown` і перезапуск Docker Desktop.

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

### Фаза 3 — ArgoCD (Terraform) + app-of-apps

```powershell
cd terraform\argocd
terraform init
terraform apply
cd ..\..
kubectl apply -f .\argocd\root-app.yaml
```

Перевірка:
```powershell
kubectl get pods -n infra-tools
kubectl get applications -n infra-tools
```
Усі поди ArgoCD мають бути `Running`. Усі Applications (`root-app`, `minio`,
`postgres`, `mlflow`, `grafana`, `prometheus`, `pushgateway`) — `Synced`/`Healthy`.

Доступ до ArgoCD UI:
```powershell
kubectl port-forward svc/argocd-server -n infra-tools 8080:443
kubectl -n infra-tools get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d
```

### Фаза 4 і далі — усі інші компоненти через ArgoCD

Починаючи з цього моменту, жодних ручних `kubectl apply`/`helm install` — усі сервіси
деплояться як ArgoCD Application з `argocd/applications/`, застосовуються через
`git push` у гілку `final-project`.

## Відомі проблеми та рішення

- **`charts.bitnami.com` Helm-репозиторій офіційно deprecated** (Broadcom/Bitnami,
  видалення завершено після 29.09.2025). Спроби `helm pull` для MinIO/PostgreSQL
  Bitnami-чартів тайм-аутяться (90с). **Рішення:** відмовились від Bitnami-чартів
  повністю, MinIO та PostgreSQL розгортаються як прості k8s-манифести
  (`k8s/minio/manifests.yaml`, `k8s/postgres/manifests.yaml`) з офіційними образами
  `minio/minio`, `postgres:16`.
- **MLflow OOMKilled на дефолтних лімітах WSL2.** Виправлено через `.wslconfig`
  (див. Фазу 1) + підняття `limits.memory` MLflow до `2Gi`.
- **Kubelet-подія "Pulling" іноді зависає**, хоча образ уже реально завантажений на
  ноду (перевіряється через `docker exec <node> crictl images`). Рішення:
  `kubectl delete pod` для форс-рестарту — новий под миттєво підхоплює вже наявний
  образ.
- **ArgoCD prune старих ресурсів після зміни джерела Application** (напр. заміна
  Helm chart на plain manifest) може затримуватись. При підозрі — форс-refresh
  (`kubectl patch application <name> --type merge -p '{"metadata":{"annotations":
  {"argocd.argoproj.io/refresh":"hard"}}}'`) або повне перестворення кластера
  (`kind delete cluster` → bootstrap з нуля за цим README) — надійніше й швидше за
  точкове дебажування залишків.

## Model Registry — запуск тренування локально

Потрібні 3 одночасні port-forward (в окремих терміналах):

```powershell
kubectl port-forward svc/mlflow -n mlops-system 5000:5000
kubectl port-forward svc/minio -n mlops-system 9000:9000
kubectl port-forward svc/pushgateway-prometheus-pushgateway -n monitoring 9091:9091
```

Python-оточення (3.12 обов'язково — 3.13 не сумісний з pyarrow):

```powershell
cd training
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python train_and_push.py
```

Результат: 5 версій моделі `iris-logistic-regression` в MLflow Model Registry, усі
автоматично в статусі `Staging`; найкраща (за accuracy) скопійована в `best_model/`.

---
*Документ доповнюється по ходу виконання проєкту (День 1-2 завершені).*