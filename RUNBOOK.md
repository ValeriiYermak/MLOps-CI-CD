# RUNBOOK

Операційні процедури для MLOps Final Project (локальний kind-fallback).
Усі команди — PowerShell, з кореня `Final_Project`, якщо не вказано інше.

## Зміст

1. [Rollout нової моделі (Staging → Production)](#1-rollout-нової-моделі-staging--production)
2. [Rollback (Production → попередня версія)](#2-rollback-production--попередня-версія)
3. [Реакція на latency-алерт (Grafana)](#3-реакція-на-latency-алерт-grafana)
4. [Реакція на model drift](#4-реакція-на-model-drift)
5. [Повний teardown інфраструктури](#5-повний-teardown-інфраструктури)
6. [Відновлення після rebuild кластера](#6-відновлення-після-rebuild-кластера)
7. [Типові інциденти та швидкі фікси](#7-типові-інциденти-та-швидкі-фікси)

---

## 1. Rollout нової моделі (Staging → Production)

**Коли застосовувати:** нова версія моделі натренована, зареєстрована в MLflow
Registry зі статусом `Staging`, метрики прийнятні, готова до продакшену.

### Крок 1 — переконатись, що модель у Staging

```powershell
kubectl port-forward svc/mlflow -n mlops-system 5000:5000
```
Відкрити `http://localhost:5000` → Models → `iris-logistic-regression` →
перевірити останню версію має stage `Staging` і тег `sha256_checksum`.

### Крок 2 — промоушен через K8s Job (не напряму з хоста)

```powershell
kubectl create -f k8s\promote-job-template.yaml
kubectl get jobs -n mlops-system
```

Job автоматично бере **останню Staging-версію**, архівує поточну Production
(переводить у `Archived`), промоутить обрану версію в `Production`.

**Промоутнути конкретну версію** (не обов'язково останню) — відредагувати
`k8s/promote-job-template.yaml`, додати аргумент `--version N` до команди
контейнера перед `kubectl create`.

### Крок 3 — перевірити завершення Job і audit-лог

```powershell
kubectl logs -n mlops-system job/<job-name> | Select-String "AUDIT"
```

Має бути рядок на кшталт `AUDIT: Модель версія N переведена в Production`.

### Крок 4 — переконатись, що inference підхопив нову версію

Ручний рестарт **не потрібен** — фоновий `_model_watcher` в inference-подах
перевіряє Production-версію кожні 30с і перезавантажує модель автоматично.

```powershell
kubectl port-forward svc/inference -n production 8080:80
Invoke-RestMethod http://localhost:8080/health
```
Очікується: `model_version` збігається з щойно промоутнутою версією.

### Крок 5 — підтвердження в Loki (аудит-трейл, C5)

```powershell
kubectl port-forward svc/loki -n monitoring 3100:3100
Invoke-RestMethod "http://localhost:3100/loki/api/v1/query_range?query={app=%22mlflow-registry-ops%22}"
```

---

## 2. Rollback (Production → попередня версія)

**Коли застосовувати:** нова Production-версія показує деградацію метрик,
підвищений error rate у Grafana, або будь-яку нештатну поведінку.

### Одна дія — Job

```powershell
kubectl create -f k8s\rollback-job-template.yaml
```

Job бере **останню `Archived`-версію**, архівує поточну (проблемну)
Production, відновлює Archived-версію в Production.

### Перевірка

Той самий процес, що й у Rollout (кроки 3-5 вище) — audit-лог, `/health`
inference-подів, Loki query.

**Обмеження:** rollback працює лише на одну версію назад (останню
Archived). Для відкату на конкретну довільну версію — промоутнути її
напряму через `promote-job-template.yaml` з `--version N`.

---

## 3. Реакція на latency-алерт (Grafana)

**Тригер:** панель "Latency p50/p95" у `inference-dashboard.json` показує
стійке зростання понад прийнятний поріг (для цього проєкту орієнтир:
p95 > 500ms стабільно протягом кількох хвилин).

### Крок 1 — підтвердити в Prometheus напряму

```powershell
kubectl port-forward svc/prometheus-server -n monitoring 9090:80
```
Query: `histogram_quantile(0.95, rate(inference_request_duration_seconds_bucket[5m]))`

### Крок 2 — перевірити CPU/Memory подів (та сама dashboard)

Якщо CPU впирається в `limits.cpu` (200m за замовчуванням для inference) —
причина в ресурсному throttling, не в моделі.

```powershell
kubectl top pod -n production
```

### Крок 3 — перевірити, який slot (blue/green) обслуговує трафік і чи є перекіс

Панель "Requests by Slot" — якщо весь трафік іде на один под (наприклад,
другий у `CrashLoopBackOff`/не Ready), це причина деградації, а не сама
модель.

```powershell
kubectl get pods -n production -o wide
kubectl describe svc inference -n production | Select-String "Endpoints"
```

### Крок 4 — рішення

- Якщо причина ресурсна → збільшити `resources.limits` у
  `k8s/inference/manifests.yaml`, закомітити, дати ArgoCD засинхронити.
- Якщо причина в самій моделі (складніша версія, повільніший inference) →
  rollback за процедурою з розділу 2.
- Якщо симптом лише в одному slot (blue або green) → перевірити логи
  конкретного пода (`kubectl logs -n production <pod>`), за потреби
  `kubectl delete pod` для форс-рестарту проблемного slot.

### Крок 5 — перевірка через логи в Loki (кореляція з latency-стрибком)

```powershell
Invoke-RestMethod "http://localhost:3100/loki/api/v1/query_range?query={namespace=%22production%22}"
```

---

## 4. Реакція на model drift

**Статус для цього проєкту:** Evidently AI / drift-моніторинг належить до
опціонального Блоку E технічного завдання (не є обов'язковою вимогою для
Definition of Done) і **не реалізований** у поточній версії проєкту —
свідоме рішення з огляду на 5-денний часовий бюджет і пріоритезацію
обов'язкових Блоків A-D.

**Якби drift-моніторинг був реалізований**, процедура виглядала б так
(задокументовано як план на майбутнє, ADR.md містить деталі trade-off):

1. Evidently AI генерує drift-звіт періодично (CronJob або окремий крок
   в Argo Workflow) порівнюючи розподіл вхідних `/predict`-запитів з
   референсним датасетом (training data).
2. При виявленні значного drift (наприклад, Data Drift Score вище порогу)
   — алерт у Grafana/Loki (структурований лог `DRIFT_ALERT:`).
3. Реакція: не автоматичний rollback (drift не завжди означає гіршу
   модель), а **тригер на перетренування** — запуск Argo Workflow
   `training-pipeline` вручну або за розкладом, з подальшою ручною
   оцінкою нової версії перед промоушеном.

---

## 5. Повний teardown інфраструктури

**Коли застосовувати:** завершення роботи над проєктом, здача,
або необхідність повністю звільнити ресурси хоста.

```powershell
kind delete cluster --name mlops-final
docker rm -f kind-registry
```

Це видаляє: увесь Kubernetes-кластер (усі поди/сервіси/дані, включно з
Model Registry — MinIO/PostgreSQL на `emptyDir`), локальний Docker registry
з усіма запушеними образами.

**Що НЕ видаляється** (і не повинно):
- Локальні Docker-образи на хості (`docker images` — `iris-inference:v1`,
  `mlflow-registry-ops:v1`, `training-pipeline:v1` лишаються в кеші Docker
  Desktop, окремому від kind)
- Git-репозиторій та вся історія — джерело правди, з якого середовище
  відновлюється

**Перевірка успішного teardown:**
```powershell
docker ps -a | Select-String mlops-final
docker ps -a | Select-String kind-registry
```
Обидві команди мають повернути порожній результат.

---

## 6. Відновлення після rebuild кластера

Детальна процедура — у README.md, розділ "Відновлення після повного
rebuild кластера". Коротко:

1. `kind create cluster` + `kind-registry` контейнер заново
2. `kubectl apply` namespaces
3. `terraform apply` (ArgoCD) — очікувати довше на холодному кеші образів
   (repo-server має явний `ARGOCD_EXEC_TIMEOUT: 5m`, тому не падає, але
   реальний час залежить від мережі)
4. `kubectl apply -f argocd\root-app.yaml` — решта стеку піднімається
   автоматично через ArgoCD sync
5. `docker push` (не обов'язково build — локальний кеш образів зазвичай
   зберігається) обох образів у новий (порожній) registry
6. Перетренувати модель (`train_and_push.py` або через Argo Workflow) +
   промоутнути (розділ 1 цього документа) — Model Registry порожній
   після rebuild через `emptyDir`-конфігурацію MinIO/PostgreSQL

---

## 7. Типові інциденти та швидкі фікси

| Симптом | Причина | Фікс |
|---|---|---|
| Inference-под `RESOURCE_DOES_NOT_EXIST` | Model Registry порожній (після rebuild) | Розділ 6 — перетренувати + промоутнути |
| Inference-под `ImagePullBackOff` | Локальний registry порожній (після rebuild) | `docker push` образу заново |
| Kubelet "Pulling" завис, хоча образ уже є | Кеш-race на конкретній ноді | `kubectl delete pod` — форс-переплан |
| ArgoCD Application `Unknown`, `helm pull`/`git fetch` timeout | repo-server без ресурсів під час масового pull | Вже виправлено постійно (`repoServer.resources` + `ARGOCD_EXEC_TIMEOUT`); якщо повторюється — `kubectl delete pod -l app.kubernetes.io/name=argocd-repo-server` |
| ArgoCD не підхопив новий коміт | Затримка автосинку (~1 хв) | `kubectl patch application <name> ... annotations "argocd.argoproj.io/refresh": "hard"` |
| Prometheus `CrashLoopBackOff`, `field global already set` | Дубльований `global:` у `serverFiles.prometheus.yml` (конфлікт з дефолтом chart'а) | Не перевизначати `global:` у `serverFiles` взагалі |
| Prometheus ConfigMap оновився, под не перезавантажив конфіг | Chart не хешує ім'я ConfigMap, под сам не рестартує | `kubectl rollout restart deployment prometheus-server -n monitoring` |
| Argo Workflow: emissary `failed to look-up entrypoint/cmd` | Executor намагається звернутись до `localhost:5001` зсередини пода (не бачить registry) | Явно вказати `command:` у container spec Workflow-кроку |
| `kubectl cluster-info` → `"system:anonymous" 403 Forbidden` одразу після рестарту Docker Desktop | API-сервер/etcd ще ініціалізуються | Зачекати ~1-2 хв, повторити — минає само |
| MLflow `OOMKilled` (exit 137) | Занижений ліміт пам'яті WSL2 | `%USERPROFILE%\.wslconfig` → `memory=8GB`, `wsl --shutdown` |
| MLflow `403 Invalid Host header` | Security middleware блокує кластерне DNS-ім'я | `extraArgs.allowed-hosts: "*"` у values MLflow |
