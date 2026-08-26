# hw_9 — MLflow Experiment Tracking + PushGateway + Grafana через ArgoCD

Цей проєкт розгортає MLflow-інфраструктуру (MinIO, PostgreSQL, MLflow
Tracking Server) та Prometheus PushGateway у вже існуючому EKS-кластері
(з hw_5) через ArgoCD, тренує кілька ML-моделей з логуванням у MLflow,
пушить метрики в PushGateway і виводить їх у Grafana через Prometheus.

## Структура проєкту

```
hw_9/
├── argocd/
│   └── applications/
│       ├── minio.yaml         # MinIO, bucket mlflow-artifacts
│       ├── postgres.yaml      # PostgreSQL, база mlflow
│       ├── mlflow.yaml        # MLflow Tracking Server, ClusterIP :5000
│       ├── pushgateway.yaml   # Prometheus PushGateway, namespace monitoring, :9091
│       ├── prometheus.yaml    # Prometheus (без Operator), namespace monitoring
│       └── grafana.yaml       # Grafana, namespace monitoring
├── experiments/
│   ├── train_and_push.py
│   └── requirements.txt
├── pod-cleanup-cronjob.yaml     # автоматична чистка "зомбі"-подів (див. нижче)
├── best_model/                 # з'являється після успішного запуску train_and_push.py
└── README.md
```

## Передумови

- Уже створений і робочий EKS-кластер (`hw_5`), `kubectl` підключений
- Встановлені `terraform`, `helm`, `kubectl`, `aws` CLI, `python` (3.10+)
- Профіль AWS CLI `goit-terraform`
- Уже розгорнутий Argo CD (`hw_7/terraform/argocd`)

> **Примітка щодо ресурсів:** кластер працює на нодах `t3.micro`
> (обмеження AWS Free Tier — 1 GB RAM, ліміт ~4 поди на ноду). Це
> найважливіший фактор, що вплинув на архітектурні рішення нижче.

## 1. Запуск Argo CD Applications

```bash
cd hw_9/argocd/applications
kubectl apply -f minio.yaml
kubectl apply -f postgres.yaml
kubectl apply -f mlflow.yaml
kubectl apply -f pushgateway.yaml
kubectl apply -f prometheus.yaml
kubectl apply -f grafana.yaml
```

Перед цим у кластері має бути виконано:
```bash
kubectl scale deployment coredns -n kube-system --replicas=1
kubectl apply -f hw_9/pod-cleanup-cronjob.yaml
```
(звільняє слот подів на `t3.micro` та вмикає автоматичну чистку
"зомбі"-подів — див. "Архітектурні рішення" нижче).

### Перевірка статусу Applications

```bash
kubectl get applications -n infra-tools
```

Очікується `Synced` для всіх шести Applications. `Health` для `mlflow`
може залишатись `Degraded` — див. розділ "Відома проблема: MLflow" нижче.

## 2. Перевірка, що MLflow і PushGateway є в кластері

```bash
kubectl get pods -n mlflow
kubectl get pods -n monitoring
```

Очікувані компоненти:
- `mlflow`, `minio`, `postgres-postgresql-0` — у namespace `mlflow`
- `pushgateway-prometheus-pushgateway`, `prometheus-server`, `grafana` —
  у namespace `monitoring`

## 3. Port-forward до сервісів

```bash
# MLflow UI
kubectl port-forward svc/mlflow -n mlflow 5000:5000

# MinIO (S3 API, потрібен для train_and_push.py)
kubectl port-forward svc/minio -n mlflow 9000:9000

# PushGateway
kubectl port-forward svc/pushgateway-prometheus-pushgateway -n monitoring 9091:9091

# Prometheus
kubectl port-forward svc/prometheus-server -n monitoring 9090:80

# Grafana
kubectl port-forward svc/grafana -n monitoring 3000:80
```

Кожна команда займає окреме вікно термінала (тунель тримається, поки
команда виконується).

**Grafana UI:** http://localhost:3000
Логін: `admin` / Пароль: `admin123`

## 4. Запуск train_and_push.py

```bash
cd hw_9/experiments
pip install -r requirements.txt --break-system-packages
python train_and_push.py
```

Скрипт (за наявності активних port-forward до MLflow :5000 та MinIO
:9000):
1. завантажує датасет Iris;
2. тренує 5 моделей `LogisticRegression` з різними `C`/`max_iter`;
3. для кожного запуску логує параметри, метрики (`accuracy`, `loss`) та
   модель-артефакт у MLflow, і пушить `mlflow_accuracy`/`mlflow_loss` (з
   міткою `run_id`) у PushGateway;
4. знаходить запуск з найкращою `accuracy` і копіює модель у
   `./best_model/`.

Змінні оточення (усі опційні, дефолти розраховані на port-forward):
`MLFLOW_TRACKING_URI`, `PUSHGATEWAY_URL`, `MLFLOW_EXPERIMENT`,
`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `MLFLOW_S3_ENDPOINT_URL`.

## 5. Перегляд метрик у Grafana

1. Відкрити http://localhost:3000, увійти (`admin`/`admin123`).
2. **Explore** (іконка компаса в лівому меню) → обрати джерело даних
   **Prometheus**.
3. У полі запиту ввести:
   ```
   mlflow_accuracy
   ```
   і окремо:
   ```
   mlflow_loss
   ```
4. Перемкнути вигляд на **Table** для табличного відображення значень
   по кожному `run_id`, або залишити **Graph** для візуалізації.

**Перевірка ланцюжка PushGateway → Prometheus вручну** (незалежно від
MLflow, корисно для діагностики):
```bash
curl.exe -X POST "http://localhost:9091/metrics/job/mlflow_training/run_id/test-run-001" --data-binary "mlflow_accuracy 0.95`n"
curl.exe "http://localhost:9090/api/v1/query?query=mlflow_accuracy"
```
Цей ланцюжок був перевірений і підтверджений робочим незалежно від
статусу MLflow-пода.

## Архітектурні рішення, зумовлені обмеженнями t3.micro

Кластер на нодах `t3.micro` (1 GB RAM, ліміт ~4 поди/нода через
обмеження ENI для AWS VPC CNI) físично не вміщує "з коробки" повний
стек Argo CD + MLflow + monitoring. Ужиті заходи:

- **Argo CD**: `applicationSet.replicas: 0` (ApplicationSet-контролер
  не використовується в цьому завданні — Applications застосовуються
  напряму через `kubectl apply`); `repoServer.resources.limits.memory`
  збільшено до 1Gi (Bitnami-репозиторій має великий `index.yaml`, парсинг
  якого призводив до `OOMKilled` при дефолтних лімітах).
- **coredns**: масштабовано з 2 до 1 репліки.
- **MinIO / PostgreSQL**: `persistence.enabled: false` — дані
  зберігаються в `emptyDir`, а не на EBS-диску. Це усуває потребу у AWS
  EBS CSI Driver (котрий сам по собі займає 5+ подів: controller +
  node-daemonset на кожній ноді) і пов'язані з ним проблеми
  топології/Availability Zone при динамічному провіжні EBS-томів. Ціна
  рішення: дані MinIO/PostgreSQL втрачаються при перезапуску пода — для
  навчального завдання це прийнятно.
- **MinIO / PostgreSQL образи**: явно вказано `bitnamilegacy/*`
  замість `bitnami/*` — Bitnami перенесла старі версії образів у
  архівний репозиторій, стандартні `docker.io/bitnami/...` тег вже
  недоступний.
- **PostgreSQL**: додано `global.imagePullSecrets: []` — без цього
  явного значення шаблон чарту падає з помилкою `nil pointer evaluating
  interface {}.pullSecrets` у певних версіях.
- **Prometheus**: використано простий чарт `prometheus` (community)
  замість `kube-prometheus-stack`, щоб уникнути окремого поду
  Prometheus Operator; вимкнено Alertmanager, kube-state-metrics,
  node-exporter, вбудований pushgateway-субчарт (є власний, окремий
  Application). Grafana data source налаштований вручну (без Operator
  автопідключення). У scrape-конфігурації використано повну назву
  сервісу PushGateway (`pushgateway-prometheus-pushgateway`, а не
  просто `pushgateway`) — саме таке ім'я генерує Helm-реліз з назвою
  `pushgateway` для чарту `prometheus-pushgateway`.
- **Автоматична чистка "зомбі"-подів**: додано CronJob
  (`hw_9/pod-cleanup-cronjob.yaml`), що кожні 2 хвилини видаляє поди в
  будь-якому стані, відмінному від `Running`/`Pending`, по всьому
  кластеру. Без нього нестабільний MLflow-под (див. нижче) за кілька
  годин накопичував сотні "мертвих" подів, які продовжували займати
  ліміт кількості подів на нодах (`t3.micro` дозволяє ~4 поди на ноду)
  навіть у статусі `Completed`/`Error`/`ContainerStatusUnknown`,
  заважаючи плануванню нових, живих подів.

## Відома проблема: MLflow Tracking Server

**Статус:** MLflow-под нестабільний — регулярно завершується з
`OOMKilled` (`Exit Code 137`, `Reason: Evicted`/`OOMKilled`) на нодах
`t3.micro`.

**Діагностика:**
```bash
kubectl get pods -n mlflow
kubectl describe pod <ім'я-пода-mlflow> -n mlflow
kubectl logs <ім'я-пода-mlflow> -n mlflow --tail=50
```
`describe` стабільно показує `Reason: OOMKilled`, `Exit Code: 137`.
Логи показують повторювані `"Waiting for child process"` /
`"Child process died"` — worker-процес MLflow-сервера (образ
`burakince/mlflow:3.15.1`, MLflow 3.x) вбивається kubelet-ом через
нестачу пам'яті на ноді.

**Що вже спробувано (без стабільного результату):**
- Збільшення `resources.limits.memory` послідовно: 512Mi → 768Mi → 1Gi
- `extraArgs.workers: "1"` (обмеження кількості worker-процесів)
- `telemetry.enabled: false`
- `GUNICORN_CMD_ARGS` з обмеженням `--max-requests`

**Висновок:** MLflow 3.x у цій конфігурації чарту потребує більше
пам'яті, ніж реально доступно на вузлі `t3.micro` після вирахування
системного резерву (`aws-node`, `kube-proxy` та інших DaemonSet-ів).
Збільшення розміру ноди (наприклад, `t3.small`, той самий обсяг vCPU,
але вдвічі більше RAM і майже втричі вищий ліміт подів на ноду) —
очікувано вирішило б проблему, але виходить за межі AWS Free Tier,
тому в межах цього завдання інфраструктура свідомо залишена на
`t3.micro`, а причина падіння — задокументована тут, а не прихована.

**Що працює стабільно, попри цю проблему:** MinIO, PostgreSQL,
PushGateway, Prometheus, Grafana, ланцюжок PushGateway → Prometheus →
Grafana Explore (перевірено вручну тестовими метриками
`mlflow_accuracy`/`mlflow_loss`, скріншоти в `screenshots/`) —
розгорнуті через ArgoCD і функціонують без зауважень.

**Наслідок для `train_and_push.py`:** через нестабільність MLflow-пода
не вдалось провести живий, безперервний прогін скрипту проти реального
запущеного MLflow Tracking Server (з'єднання уривались через кілька
секунд-хвилин після старту пода). Скрипт написаний, перевірений на
коректність коду і логіки, і готовий до запуску за наявності стабільного
MLflow (наприклад, на нодах більшого розміру). Робочість ланцюжка
PushGateway → Prometheus → Grafana підтверджена окремо, тестовими
метриками, що надіслані напряму через `curl`, минаючи MLflow — це
демонструє коректність усієї частини стеку, яка не залежить від MLflow.

## Видалення ресурсів

Порядок зворотний до створення:

```bash
# 1. Видалити Applications MLflow/monitoring-стеку
cd hw_9/argocd/applications
kubectl delete -f mlflow.yaml
kubectl delete -f postgres.yaml
kubectl delete -f minio.yaml
kubectl delete -f pushgateway.yaml
kubectl delete -f prometheus.yaml
kubectl delete -f grafana.yaml
kubectl delete namespace mlflow --ignore-not-found

# 2. Видалити Argo CD
cd ../../../hw_7/terraform/argocd
terraform destroy

# 3. Видалити EKS-кластер, потім VPC
cd ../../../hw_5/eks-vpc-cluster/eks
terraform destroy

cd ../vpc
terraform destroy

# 4. Прибрати старі state-файли в S3 (опційно, перед повторним підняттям)
aws s3 rm s3://tfstate-goit/vpc/terraform.tfstate --profile goit-terraform
aws s3 rm s3://tfstate-goit/eks/terraform.tfstate --profile goit-terraform
aws s3 rm s3://tfstate-goit/argocd/terraform.tfstate --profile goit-terraform
```

Після видалення варто перевірити відсутність EC2-інстансів, NAT
Gateway та Elastic IP вручну через AWS CLI/Console, щоб уникнути
несподіваних витрат.