# MLOps Final Project

MLOps-платформа: MLflow Model Registry, promotion workflow (Staging → Production),
Blue-Green deployment, моніторинг (Prometheus + Grafana + Loki), security baseline.

Модель: Iris LogisticRegression (5 версій гіперпараметрів), тренування <1 хв.

## Документація проєкту

- **README.md** (цей файл) — архітектура, bootstrap, структура репозиторію
- **[RUNBOOK.md](./RUNBOOK.md)** — операційні процедури: rollout, rollback,
  реакція на latency-алерт, drift, повний teardown, типові інциденти
- **[ADR.md](./ADR.md)** — чому Blue-Green (не Canary/A-B), trade-offs,
  альтернативи, що зробили б інакше
- **[THREAT_MODEL.md](./THREAT_MODEL.md)** — C6, 5 загроз і контрзаходи,
  результат git-secrets скану репозиторію

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
| AWS Step Functions | Argo Workflows (`workflows/training-workflow-template.yaml`) | ✅ |
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
│  ┌───────────┐ ┌─────────┐ ┌────────┐ ┌──────────┐  ┌──────────────────────────┐  │
│  │ Prometheus│ │ Grafana │ │  Loki  │ │ Promtail │  │ inference-blue / green    │◀───┘
│  │ +Pushgw   │ │ (Prom+  │ │ (logs) │ │(DaemonSet│  │ (FastAPI, Blue-Green,     │
│  │           │ │  Loki ds)│ │        │ │ per node)│  │  RBAC, checksum-verify)   │
│  └───────────┘ └─────────┘ └────────┘ └──────────┘  └──────────────────────────┘  │
│                                                                                     │
│  namespace: workflows                                                              │
│  ┌────────────────────────────────────────────────────────┐                       │
│  │  Argo Workflows (validate-env → train-and-register)     │                       │
│  │  заміна AWS Step Functions/Lambda з hw_10                │                       │
│  └────────────────────────────────────────────────────────┘                       │
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
├── README.md                  # цей файл
├── RUNBOOK.md                 # операційні процедури
├── ADR.md                     # architecture decision record
├── THREAT_MODEL.md            # C6 + git-secrets скан
├── kind/                    # конфігурація kind-кластера
├── k8s/
│   ├── namespaces/          # bootstrap-манифест namespaces
│   ├── minio/                # plain Deployment+Service+Job (заміна Bitnami chart)
│   ├── postgres/             # plain Deployment+Service (заміна Bitnami chart)
│   ├── loki/                 # plain Deployment+ConfigMap (заміна офіційного Helm chart)
│   ├── inference/            # Blue-Green Deployments (blue/green) + Service
│   ├── promote-job-template.yaml   # K8s Job: Staging → Production (audit trail)
│   └── rollback-job-template.yaml  # K8s Job: rollback останньої Archived-версії
├── terraform/
│   └── argocd/               # Terraform-модуль: ArgoCD через helm_release
├── argocd/
│   ├── root-app.yaml          # кореневий Application (app-of-apps)
│   └── applications/          # ArgoCD Application-манифести (джерело правди для деплоїв)
│       └── argo-workflows.yaml  # Argo Workflows (заміна hw_10 Step Functions)
├── workflows/
│   ├── training-workflow-template.yaml  # WorkflowTemplate: validate-env → train-and-register
│   ├── training-workflow-run.yaml       # одноразовий запуск (kubectl create, без argo CLI)
│   └── pod-cleanup-cronjob.yaml
├── training/
│   ├── train_and_push.py      # тренування + реєстрація в MLflow Registry + checksum
│   ├── Dockerfile              # образ для Argo Workflow train-and-register кроку
│   ├── registry/
│   │   ├── promote_to_production.py   # Staging → Production (окрема дія, B2)
│   │   ├── rollback.py                # Production → Archived → Production (B4)
│   │   └── Dockerfile                 # образ для promote/rollback K8s Jobs (C5)
│   ├── requirements.txt
│   └── .venv/                 # Python 3.12 venv (не в git)
├── inference/
│   ├── app/
│   │   ├── main.py            # FastAPI: /predict, /health, /metrics, background _model_watcher
│   │   ├── schemas.py         # Pydantic input validation (C1)
│   │   └── model_loader.py    # завантаження з Registry + checksum-перевірка (C4)
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .venv/                 # (не в git)
├── rbac/                      # C3: mlops-engineer (staging/production), viewer ролі
├── dashboards/
│   └── inference-dashboard.json   # Grafana dashboard (6 панелей, A5)
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
- `monitoring` — Prometheus, Grafana, Loki, Promtail
- `workflows` — Argo Workflows (створюється автоматично, `CreateNamespace=true`)

### Фаза 3 — ArgoCD (Terraform) + app-of-apps

```powershell
cd terraform\argocd
terraform init
terraform apply
cd ..\..
kubectl apply -f .\argocd\root-app.yaml
```

**Важливо (перше розгортання "з нуля" на порожньому Docker-кеші):** helm-реліз ArgoCD
за замовчуванням має timeout 600с. При повністю холодному кеші образів (перший
`kind create cluster` на машині/після повного видалення) одночасний pull ~5 образів
ArgoCD може не встигнути завершитись — repo-server, зокрема, потребує явних ресурсів
(інакше власний `git fetch` не встигає за дефолтні 90с `ARGOCD_EXEC_TIMEOUT`). У
`terraform/argocd/values/argocd-values.yaml` це вирішено додаванням явного
`repoServer.resources` + `ARGOCD_EXEC_TIMEOUT: "5m"`. Якщо окремий под все одно
застряг у `ContainerCreating`/`Init` довше за інші (кеш-race на конкретній ноді,
`crictl images` показує образ уже присутнім) — просто `kubectl delete pod` для
форс-перестворення, без зміни конфігурації.

Перевірка:
```powershell
kubectl get pods -n infra-tools
kubectl get applications -n infra-tools
```
Усі Applications (`root-app`, `minio`, `postgres`, `mlflow`, `loki`, `promtail`,
`grafana`, `prometheus`, `pushgateway`, `inference`, `argo-workflows`) мають бути
`Synced`/`Healthy`.

Доступ до ArgoCD UI:
```powershell
kubectl port-forward svc/argocd-server -n infra-tools 8080:443
kubectl -n infra-tools get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d
```

### Фаза 4 і далі — усі інші компоненти через ArgoCD

Починаючи з цього моменту, жодних ручних `kubectl apply`/`helm install` — усі сервіси
деплояться як ArgoCD Application з `argocd/applications/`, застосовуються через
`git push` у гілку `final-project`. Якщо ArgoCD не підхопив новий коміт одразу
(інтервал автосинку ~1 хв) — форс-refresh:
```powershell
kubectl patch application <name> -n infra-tools --type merge -p '{"metadata":{"annotations":{"argocd.argoproj.io/refresh":"hard"}}}'
```

### Фаза 5 — тренувальний пайплайн (Argo Workflows, заміна hw_10)

WorkflowTemplate застосовується один раз вручну (не через ArgoCD — це шаблон
дій, а не steady-state ресурс):

```powershell
kubectl apply -f workflows\training-workflow-template.yaml
```

Запуск тренування (без `argo` CLI — через звичайний `kubectl create` з
одноразовим Workflow-об'єктом):

```powershell
kubectl create -f workflows\training-workflow-run.yaml
kubectl get workflows -n workflows
```

Два кроки: `validate-env` (перевірка доступності MLflow), `train-and-register`
(повний train_and_push.py — тренування, реєстрація версій, checksum, push
метрик у PushGateway).

### Відновлення після повного rebuild кластера

MinIO та PostgreSQL використовують `emptyDir` (свідомий trade-off — не потрібен
PVC/EBS CSI для навчального проєкту). Це означає, що повний `kind delete cluster`
знищує Model Registry (MLflow) і локальний Docker registry (`kind-registry`,
окремий контейнер, теж пересоздається порожнім). Перевірена послідовність повного
відновлення:

```powershell
kind delete cluster --name mlops-final
docker rm -f kind-registry
docker run -d --restart=always -p 127.0.0.1:5001:5000 --name kind-registry registry:2
kind create cluster --config .\kind\kind-config.yaml
docker network connect kind kind-registry
kubectl apply -f .\k8s\namespaces\namespaces.yaml
cd terraform\argocd; terraform apply -auto-approve; cd ..\..
kubectl apply -f .\argocd\root-app.yaml
```

Дати всім Applications стабілізуватись (`kubectl get applications -n infra-tools`),
потім обов'язково перезібрати й запушити всі три Docker-образи (registry порожній
після rebuild — локальні образи на хості зазвичай зберігаються, `docker push`
спрацює навіть без повторного `docker build`, якщо код не змінювався):

```powershell
docker push localhost:5001/iris-inference:v1
docker push localhost:5001/mlflow-registry-ops:v1
docker push localhost:5001/training-pipeline:v1
```

Далі — перетренувати модель і промоутнути версію в Production (Model Registry
порожній після rebuild) через Argo Workflow (Фаза 5) або напряму:

```powershell
kubectl apply -f workflows\training-workflow-template.yaml
kubectl create -f workflows\training-workflow-run.yaml
kubectl create -f k8s\promote-job-template.yaml
```

Inference-поди самостійно підхоплять нову Production-версію протягом 30с
(background `_model_watcher`), без ручного `kubectl delete pod`. Детальна
операційна процедура — у [RUNBOOK.md](./RUNBOOK.md).

## Відомі проблеми та рішення

Повна таблиця типових інцидентів і швидких фіксів — у
[RUNBOOK.md, розділ 7](./RUNBOOK.md#7-типові-інциденти-та-швидкі-фікси).
Найважливіші, коротко:

- **`charts.bitnami.com` Helm-репозиторій офіційно deprecated.** MinIO та
  PostgreSQL — прості k8s-манифести (`k8s/minio/`, `k8s/postgres/`) з
  офіційними образами замість Bitnami-чартів.
- **Офіційний Helm chart `grafana/loki` тягне зайвий Grafana Agent Operator.**
  Loki розгорнуто як простий манифест (`k8s/loki/`), образ `grafana/loki:2.9.6`
  напряму.
- **MLflow OOMKilled на дефолтних лімітах WSL2** — `.wslconfig` (Фаза 1).
- **MLflow 3.x "Invalid Host header" (DNS rebinding protection)** —
  `extraArgs.allowed-hosts: "*"` у values MLflow.
- **Inference-под не оновлював модель без ручного рестарту** — фоновий
  `_model_watcher` (30с інтервал) в `inference/app/main.py`.
- **Дублювання `global:` у Prometheus `serverFiles`** спричиняло
  `CrashLoopBackOff` — не перевизначати `global:`, лишити дефолт chart'а.
- **ArgoCD `helm pull`/`git fetch` timeout на холодному старті** —
  `repoServer.resources` + `ARGOCD_EXEC_TIMEOUT: "5m"`.
- **Argo Workflows emissary executor не може ввести образ через
  `localhost:5001` зсередини пода** — явний `command:` у container spec
  замість покладання на автовизначення ENTRYPOINT.

## Model Registry — тренування, промоушен, rollback

Потрібні 3 одночасні port-forward (в окремих терміналах) — **або** тренування
через Argo Workflow (Фаза 5 вище, не потребує port-forward, DNS вирішується
всередині кластера):
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

**Промоушен у Production — контейнеризовано як K8s Job** (не host-скрипт напряму;
причина: аудит-трейл (C5) має бути довірений, stdout поду автоматично йде в Loki
через Promtail):
```powershell
kubectl create -f k8s\promote-job-template.yaml
```

**Rollback** (одна дія — вимога B4):
```powershell
kubectl create -f k8s\rollback-job-template.yaml
```

Обидва Job логують `AUDIT:`-рядки, перевірені видимими в Loki через
`Invoke-RestMethod http://localhost:3100/loki/api/v1/query_range` (потрібен
port-forward `svc/loki -n monitoring 3100:3100`). Повна процедура — у
[RUNBOOK.md, розділи 1-2](./RUNBOOK.md).

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
(`blue`/`green`). Фоновий watcher автоматично перезавантажує модель при
промоушені/rollback — ручний рестарт подів не потрібен. Обґрунтування вибору
Blue-Green (не Canary/A-B) — [ADR.md](./ADR.md).

Перевірка:
```powershell
kubectl port-forward svc/inference -n production 8080:80
```
`http://localhost:8080/health` → `{"status":"ok","model_version":"...","model_stage":"Production"}`

**Security (Блок C)** — деталі загроз і контрзаходів у
[THREAT_MODEL.md](./THREAT_MODEL.md):
- C1 — Pydantic-валідація входу, HTTP 400 без витоку внутрішніх деталей
- C2 — rate limiting 30 запитів/хв на `/predict` (slowapi)
- C3 — RBAC-ролі в `rbac/`: `mlops-engineer`, `viewer`
- C4 — immutable model artifacts: SHA256-checksum перевіряється перед
  завантаженням моделі
- C5 — audit logging: promote/rollback як K8s Jobs, stdout → Promtail → Loki
- C6 — threat model + git-secrets скан репозиторію: [THREAT_MODEL.md](./THREAT_MODEL.md)

## Моніторинг (Prometheus + Grafana + Loki)

Grafana dashboard `dashboards/inference-dashboard.json` (6 панелей): Request Rate by
status, Latency p50/p95, Error Rate by type, CPU подів inference, Memory подів
(RSS), Requests by Slot (blue/green). Datasources: Prometheus + Loki.

Scrape jobs (Prometheus, `argocd/applications/prometheus.yaml`): `prometheus`,
`pushgateway`, `inference` (kubernetes_sd, namespace `production`, лейбли
`slot`/`pod`), `kubernetes-cadvisor` (CPU/RAM подів через node role).

---
*Статус: Блоки A-D технічно завершені (архітектура, promotion workflow,
security baseline, документація). Залишається: фінальний
teardown+rebuild-from-README демо-прогін, скріншоти, демо-відео, live-демо
з ментором.*