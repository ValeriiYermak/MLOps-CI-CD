hw_7 — Розгортання Argo CD через Terraform + GitOps
Цей проєкт розгортає Argo CD у вже існуючому EKS-кластері (створеному в
hw_5) через Terraform, і налаштовує GitOps-деплой демозастосунку через
Argo CD `ApplicationSet`.
Структура проєкту
```
hw_7/
├── terraform/
│   └── argocd/
│       ├── main.tf          # helm_release "argocd"
│       ├── variables.tf
│       ├── provider.tf      # helm + aws провайдери, підключення до EKS
│       ├── outputs.tf
│       ├── terraform.tf
│       ├── backend.tf       # S3 state (key: argocd/terraform.tfstate)
│       └── values/
│           └── argocd-values.yaml
├── applicationset.yaml       # ApplicationSet-маніфест (застосовується вручну)
└── goit-argo/                 # GitOps-репозиторій, за яким стежить ApplicationSet
    └── namespace/
        ├── application/
        │   ├── ns.yaml
        │   └── demo-nginx.yaml
        └── infra-tools/
            └── ns.yaml
```
Git-репозиторій зі структурою `namespace/*`:
https://github.com/ValeriiYermak/MLOps-CI-CD/tree/lesson_3/hw_7/goit-argo
Передумови
Уже створений і робочий EKS-кластер (`hw_5`), `kubectl` підключений
(`aws eks update-kubeconfig`)
Встановлені `terraform`, `helm`, `kubectl`, `aws` CLI
Профіль AWS CLI `goit-terraform`
1. Запуск Terraform (розгортання Argo CD)
```bash
cd hw_7/terraform/argocd
terraform init
terraform plan
terraform apply
```
Terraform підключається до вже існуючого кластера через `data "aws_eks_cluster"` (за назвою `mlops-eks-cluster`) і встановлює Argo CD
як `helm_release` у namespace `infra-tools` з налаштуваннями з
`values/argocd-values.yaml` (ClusterIP-сервіс, `--insecure` extraArgs,
RBAC-політики, resync-таймаут контролера).
> **Примітка щодо ресурсів:** кластер використовує ноди `t3.micro`
> (обмеження AWS Free Tier), які мають жорсткий ліміт кількості подів
> на ноду (обмеження ENI для AWS VPC CNI, ~4 поди/нода). Через це:
> - у `argocd-values.yaml` вимкнено необов'язкові компоненти Dex
>   (`dex.enabled: false`) та Notifications Controller
>   (`notifications.enabled: false`);
> - кількість нод у `cpu-nodes` збільшено з 2 до 3
>   (`aws eks update-nodegroup-config --scaling-config
>   desiredSize=3`), щоб вистачило місця для решти компонентів Argo CD
>   і demo-застосунку.
2. Перевірка, що Argo CD працює
```bash
kubectl get pods -n infra-tools
```
Очікуваний результат — кілька подів з префіксом `argocd-` у статусі
`Running`:
```
argocd-application-controller-0
argocd-applicationset-controller-...
argocd-redis-...
argocd-repo-server-...
argocd-server-...
```
3. Відкриття Argo CD UI
Сервіс `argocd-server` має тип `ClusterIP`, тому доступ — лише через
port-forward:
```bash
kubectl port-forward svc/argocd-server -n infra-tools 8080:443
```
Відкрити в браузері: `https://localhost:8080` (сертифікат самопідписаний,
браузер попередить — підтвердити перехід).
Логін: `admin`
Пароль — початковий пароль адміністратора зберігається в
Kubernetes secret:
```bash
kubectl -n infra-tools get secret argocd-initial-admin-secret \
  -o jsonpath="{.data.password}" | base64 -d
```
4. ApplicationSet і GitOps-репозиторій
`ApplicationSet` (`hw_7/applicationset.yaml`) сканує директорію
`hw_7/goit-argo/namespace/*` у гілці `lesson_3` репозиторію
`MLOps-CI-CD` і автоматично створює окремий Argo CD `Application` для
кожної знайденої підпапки (`application`, `infra-tools`).
Застосувати ApplicationSet до кластера (одноразово):
```bash
kubectl apply -f hw_7/applicationset.yaml
```
Перевірити, що Applications створені:
```bash
kubectl get applications -n infra-tools
```
Очікуваний результат:
```
NAME          SYNC STATUS   HEALTH STATUS
application   Synced        Healthy
infra-tools   Synced        Healthy
```
Синхронізація автоматична (`syncPolicy.automated`): будь-яка зміна,
закомічена та запушена в `hw_7/goit-argo/namespace/*`, підхоплюється
Argo CD без ручного втручання (перевірено на практиці — зменшення
`replicas` у `demo-nginx.yaml` з 2 до 1 автоматично прибрало зайвий под
з кластера протягом хвилини).
5. Перевірка Deployment і подів у namespace `application`
```bash
kubectl get deploy -n application
kubectl get pods -n application
```
Очікується `Deployment` `demo-nginx` та відповідний под(и) у статусі
`Running`.
6. Перевірка доступу до demo-застосунку
```bash
kubectl -n application port-forward deployment/demo-nginx 8081:80
```
Відкрити в браузері `http://localhost:8081` — має відкритись стандартна
привітальна сторінка nginx ("Welcome to nginx!").
Видалення ресурсів
Порядок зворотний до створення:
```bash
# 1. Видалити ApplicationSet
kubectl delete -f hw_7/applicationset.yaml

# ⚠️ ВАЖЛИВО: видалення ApplicationSet НЕ гарантує автоматичне видалення
# вже згенерованих ним Application-ресурсів — вони можуть залишитись
# "осиротілими" в кластері (Argo CD більше ними не керує, sync/prune
# більше не відбувається, але самі об'єкти Application фізично існують).
# Перевірити та за потреби видалити вручну:
kubectl get applications -n infra-tools
kubectl delete applications --all -n infra-tools

# Переконатись, що ресурси demo-застосунку теж прибрані
# (якщо ApplicationSet встиг видалитись до prune — видалити namespace вручну):
kubectl get pods -n application
kubectl delete namespace application --ignore-not-found

# 2. Видалити Argo CD
cd hw_7/terraform/argocd
terraform destroy

# ⚠️ ВАЖЛИВО: якщо namespace infra-tools "зависає" в статусі Terminating
# (перевірити: kubectl get namespace infra-tools), причина зазвичай —
# застряглі Application-об'єкти з finalizer resources-finalizer.argocd.argoproj.io
# (Argo CD-контролер, який мав би підтвердити очищення, вже видалений разом
# з релізом, тому finalizer нікому "відпустити"). Перевірити та прибрати вручну:
kubectl get applications -n infra-tools
kubectl patch application <ім'я> -n infra-tools -p '{"metadata":{"finalizers":null}}' --type=merge
# (повторити для кожного застряглого Application; після цього namespace
# видаляється одразу)

# 3. Видалити EKS-кластер, потім VPC
# Порядок важливий — EKS-кластер і його node group-и розташовані всередині
# VPC і залежать від неї, тому спочатку видаляється кластер, а вже потім мережа.
cd ../../../hw_5/eks-vpc-cluster/eks
terraform destroy

cd ../vpc
terraform destroy
```