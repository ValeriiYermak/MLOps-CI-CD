# eks-vpc-cluster

Terraform-проєкт для створення базової AWS-інфраструктури під майбутні
ML-сервіси: VPC + EKS-кластер з двома node group-ами (`cpu-nodes` та
`gpu-nodes`).

## Структура проєкту

```
eks-vpc-cluster/
├── vpc/          # створює VPC, subnet-и, NAT gateway
│   ├── main.tf
│   ├── variables.tf
│   ├── outputs.tf
│   ├── terraform.tf
│   └── backend.tf
├── eks/          # створює EKS-кластер + node group-и, читає VPC через remote_state
│   ├── main.tf
│   ├── variables.tf
│   ├── outputs.tf
│   ├── terraform.tf
│   ├── backend.tf
│   └── data.tf
└── README.md
```

`vpc/` і `eks/` — незалежні Terraform-конфігурації без спільного
кореневого `main.tf`. Вони обмінюються даними через **S3 remote state**:
`vpc/` після `apply` зберігає output-и в
`s3://tfstate-goit/vpc/terraform.tfstate`, а `eks/` читає їх звідти через
`data "terraform_remote_state" "vpc"` у файлі `eks/data.tf`.

## Про gpu-nodes

Node group `gpu-nodes` в цьому проєкті створена **не на справжніх
GPU-інстансах**, а на звичайних `t3.micro`. Причина: AWS-акаунт, на
якому виконувалось завдання, має обмеження Free Tier — спроба запустити
`t3.medium`/`t3.large` завершувалась помилкою
`InvalidParameterCombination - not eligible for Free Tier`, тому обидві
node group-и (`cpu-nodes` і `gpu-nodes`) використовують `t3.micro`.

Незважаючи на однаковий тип інстансу, принцип **workload-ізоляції**
реалізовано на рівні Kubernetes-лейблів: кожна node group отримує лейбл
`workload-type` (`cpu` або `gpu`), що підтверджується командою:

```bash
kubectl get nodes -L workload-type
```

Для отримання справжньої GPU node group достатньо в `eks/variables.tf`
змінити `gpu_node_instance_types` на реальний GPU-інстанс (наприклад,
`["g4dn.xlarge"]`) — за умови, що акаунт більше не обмежений Free Tier.

## Передумови

1. Встановлені: `terraform` (>= 1.5), `aws` CLI (v2), `kubectl`.
2. Налаштований AWS CLI профіль `goit-terraform`
   (`aws configure --profile goit-terraform`).
3. Заздалегідь створений S3 bucket для state (у цьому проєкті —
   `tfstate-goit`, регіон `us-east-1`).

## Порядок запуску

### 1. Створення VPC

```bash
cd vpc
terraform init
terraform plan
terraform apply
```

Після успішного `apply` перевірити output-и:

```bash
terraform output
```

Мають з'явитись `vpc_id`, `public_subnets`, `private_subnets`.

### 2. Створення EKS-кластера

```bash
cd ../eks
terraform init
terraform plan
terraform apply
```

Створення EKS control plane займає орієнтовно 12–20 хвилин.

### 3. Підключення kubectl

```bash
aws eks --region us-east-1 --profile goit-terraform update-kubeconfig \
  --name mlops-eks-cluster
```

(Готову команду з правильними значеннями можна також взяти з
`terraform output update_kubeconfig_command` у папці `eks/`.)

### 4. Перевірка нод

```bash
kubectl get nodes
```

Очікується побачити 3 ноди (2 у `cpu-nodes`, 1 у `gpu-nodes`) у статусі
`Ready`. Перевірка лейблів:

```bash
kubectl get nodes -L workload-type
```

## Видалення ресурсів

Порядок зворотний до створення — спочатку EKS, потім VPC, бо EKS-кластер
і його node group-и розташовані всередині VPC і залежать від неї.

```bash
cd eks
terraform destroy

cd ../vpc
terraform destroy
```

## Типові проблеми (з реального проходження завдання)

- **`AsgInstanceLaunchFailures: ... not eligible for Free Tier`** —
  акаунт обмежений Free Tier; потрібно використовувати `t3.micro`
  (або інший free-tier-eligible тип) в `eks/variables.tf` для обох
  node group-ів.
- **`data.terraform_remote_state.vpc` не знаходить output-и** —
  переконатись, що `vpc/terraform apply` виконано успішно ДО запуску
  `eks/terraform apply`, і що `key` в `eks/data.tf` збігається з `key`
  в `vpc/backend.tf` (`vpc/terraform.tfstate`).
- **`kubectl get nodes` нічого не показує** — перевірити, що
  update-kubeconfig виконано з правильним `--region` і `--profile`, і
  що IAM-користувач, яким виконувався `terraform apply` в `eks/`, це
  той самий, яким запускається `kubectl` (завдяки
  `enable_cluster_creator_admin_permissions = true` саме він отримує
  admin-доступ до кластера).