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
| AWS Step Functions | Argo Workflows / GitLab CI | заплановано (День 4) |
| AWS IAM | Kubernetes ServiceAccounts + RBAC | ✅ (rbac/) |
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
│  namespace: monitoring           namespace: production                  │          │
│  ┌───────────┐ ┌─────────┐       ┌──────────────────────────────┐      │          │
│  │ Prometheus│ │ Grafana │       │  inference-blue / inference-green│◀────┘          │
│  │ +Pushgw   │ │ (+Loki, │       │  (FastAPI, Blue-Green, RBAC)    │                 │
│  │           │ │  План.) │       │  завантажує модель + checksum   │                 │
│  └───────────┘ └─────────┘       └──────────────────────────────┘                  │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────┘
        ▲
        │ git push
┌───────┴────────┐
│  GitHub repo    │  ValeriiYermak/MLOps-CI-CD, гілка final-project
│  (джерело правди│  argocd/applications/*.yaml, k8s/*, terraform/*, rbac/*
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
| Python (training/inference) | 3.12 (3.13 несумісний з pyarrow — немає готового wheel) |

## Структура репозиторію

```
Final_Project/
├── kind/                    # конфігурація kind-кластера
├── k8s/
│   ├── namespaces/          # bootstrap-манифест namespaces
│   ├── minio/                # plain Deployment+Service+Job (заміна Bitnami chart)
│   ├── postgres/             # plain Deployment+Service (заміна Bitnami chart)
│   └── inference/            # Blue-Green Deployments (blue/green) + Service
├── terraform/
│   └── argocd/               # Terraform-модуль: ArgoCD через helm_release
├── argocd/
│   ├── root-app.yaml          # кореневий Application (app-of-apps)
│   └── applications/          # ArgoCD Application-манифести (джерело правди для деплоїв)
├── training/
│   ├── train_and_push.py      # тренування + реєстрація в MLflow Registry + checksum
│   ├── registry/
│   │   ├── promote_to_production.py   # Staging → Production (окрема дія, B2)
│   │   └── rollback.py                # Production → Archived → Production (B4)
│   ├── requirements.txt
│   └── .venv/                 # Python 3.12 venv (не в git)
├── inference/
│   ├── app/
│   │   ├── main.py            # FastAPI: /predict, /health, /metrics
│   │   ├── schemas.py         # Pydantic input validation (C1)
│   │   └── model_loader.py    # завантаження з Registry + checksum-перевірка (C4)
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .venv/                 # (не в git)
├── rbac/                      # C3: mlops-engineer (staging/production), viewer ролі
├── workflows/                 # заміна AWS Step Functions (заплановано: Argo Workflows/CI)
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
Усі Applications (`root-app`, `minio`, `postgres`, `mlflow`, `grafana`, `prometheus`,
`pushgateway`, `inference`) мають бути `Synced`/`Healthy`.

Доступ до ArgoCD UI:
```powershell
kubectl port-forward svc/argocd-server -n infra-tools 8080:443
kubectl -n infra-tools get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d
```

### Фаза 4 і далі — усі інші компоненти через ArgoCD

Починаючи з цього моменту, жодних ручних `kubectl apply`/`helm install` — усі сервіси
деплояться як ArgoCD Application з `argocd/applications/`, застосовуються через
`git push` у гілку `final-project`. Якщо ArgoCD не підхопив новий коміт одразу
(інтервал автосинку ~3 хв) — форс-refresh:
```powershell
kubectl patch application root-app -n infra-tools --type merge -p '{"metadata":{"annotations":{"argocd.argoproj.io/refresh":"hard"}}}'
```

## Відомі проблеми та рішення

- **`charts.bitnami.com` Helm-репозиторій офіційно deprecated** (Broadcom/Bitnami,
  видалення завершено після 29.09.2025). **Рішення:** MinIO та PostgreSQL
  розгортаються як прості k8s-манифести (`k8s/minio/`, `k8s/postgres/`) з офіційними
  образами `minio/minio`, `postgres:16` замість Bitnami-чартів.
- **MLflow OOMKilled на дефолтних лімітах WSL2.** Виправлено через `.wslconfig`
  (Фаза 1) + `limits.memory: 2Gi` для MLflow.
- **MLflow 3.x: "Invalid Host header - possible DNS rebinding attack detected" (403).**
  Вбудований security middleware MLflow блокує запити з Host-заголовком, відмінним
  від `localhost` — це ламало доступ з подів через кластерне DNS-ім'я
  (`mlflow.mlops-system.svc.cluster.local`). **Рішення:** додано
  `extraArgs.allowed-hosts: "*"` у values MLflow Helm-релізу.
- **Kubelet-подія "Pulling" іноді зависає**, хоча образ уже реально завантажений на
  ноду. Рішення: `kubectl delete pod` для форс-рестарту.
- **ArgoCD prune старих ресурсів / затримка підхоплення нового коміту.** Форс-refresh
  через `kubectl patch application <name> ... annotations "argocd.argoproj.io/refresh": "hard"`,
  або за потреби повне перестворення кластера (`kind delete cluster` → bootstrap з
  нуля за цим README) — надійніше й швидше за точкове дебажування залишків.

## Model Registry — тренування, промоушен, rollback

Потрібні 3 одночасні port-forward (в окремих терміналах):
```powershell
kubectl port-forward svc/mlflow -n mlops-system 5000:5000
kubectl port-forward svc/minio -n mlops-system 9000:9000
kubectl port-forward svc/pushgateway-prometheus-pushgateway -n monitoring 9091:9091
```

**Тренування** (реєструє нові версії, автоматично Staging, рахує SHA256-checksum):
```powershell
cd training
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python train_and_push.py
```

**Промоушен у Production** (окрема дія від тренування — вимога B2):
```powershell
python registry\promote_to_production.py            # промоутить останню Staging-версію
python registry\promote_to_production.py --version 7  # або конкретну версію
```

**Rollback** (одна команда — вимога B4):
```powershell
python registry\rollback.py
```

## Inference-сервіс (FastAPI, Blue-Green)

Локальний запуск для розробки:
```powershell
cd inference
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
$env:MLFLOW_TRACKING_URI = "http://localhost:5000"
$env:AWS_ACCESS_KEY_ID = "minioadmin"
$env:AWS_SECRET_ACCESS_KEY = "minioadmin123"
$env:MLFLOW_S3_ENDPOINT_URL = "http://localhost:9000"
uvicorn app.main:app --host 0.0.0.0 --port 8000
```
Swagger UI: `http://localhost:8000/docs`

**Docker build + push у локальний registry:**
```powershell
docker build -t localhost:5001/iris-inference:v1 .
docker push localhost:5001/iris-inference:v1
```

**У кластері** (через ArgoCD, `k8s/inference/manifests.yaml`): два Deployment
(`inference-blue`, `inference-green`), один Service `inference` в namespace
`production`, перемикання трафіку — зміна `spec.selector.slot` у Service
(`blue`/`green`).

Перевірка:
```powershell
kubectl port-forward svc/inference -n production 8080:80
```
`http://localhost:8080/health` → `{"status":"ok","model_version":"...","model_stage":"Production"}`

**Security (Блок C):**
- C1 — Pydantic-валідація входу (`sepal_length/width`, `petal_length/width`), HTTP 400
  без витоку внутрішніх деталей
- C2 — rate limiting 30 запитів/хв на `/predict` (slowapi)
- C3 — RBAC-ролі в `rbac/`: `mlops-engineer` (повний доступ staging, обмежений
  production), `viewer` (read-only, ClusterRole)
- C4 — immutable model artifacts: SHA256-checksum записується як tag версії при
  тренуванні, inference перевіряє його перед завантаженням моделі (підтверджено
  робочим — сервіс відмовився завантажити версію без checksum-тега)

---
*Документ доповнюється по ходу виконання проєкту (День 1-3 завершені).*