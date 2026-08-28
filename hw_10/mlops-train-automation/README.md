# mlops-train-automation

Спрощений training pipeline на AWS: Step Function з двома послідовними
кроками (`ValidateData → LogMetrics`), реалізованими як Lambda-функції,
розгорнутий через Terraform і запускається автоматично через GitLab CI
при push у гілку `main`.

## Структура проєкту

```
mlops-train-automation/
├── terraform/
│   ├── main.tf          # IAM-ролі, Lambda-функції, Step Function
│   ├── data.tf           # data sources: caller identity, assume-role policies
│   ├── variables.tf
│   ├── outputs.tf
│   ├── terraform.tf      # required_providers
│   └── lambda/
│       ├── validate.py
│       ├── log_metrics.py
│       ├── validate.zip
│       └── log_metrics.zip
├── .gitlab-ci.yml
└── README.md
```

## Передумови

- `terraform` (>= 1.5), `aws` CLI (v2)
- Профіль AWS CLI `goit-terraform` (або власний, з правами на IAM,
  Lambda, Step Functions)
- PowerShell (Windows) для команди `Compress-Archive`, або `zip`
  (Linux/Mac)

## 1. Створення Lambda-архівів

Код Lambda-функцій уже лежить у `terraform/lambda/validate.py` та
`terraform/lambda/log_metrics.py`. Щоб зібрати (або перезібрати після
зміни коду) `.zip`-архіви:

**Windows (PowerShell):**
```powershell
cd terraform/lambda
Compress-Archive -Path validate.py -DestinationPath validate.zip -Force
Compress-Archive -Path log_metrics.py -DestinationPath log_metrics.zip -Force
```

**Linux / macOS:**
```bash
cd terraform/lambda
zip validate.zip validate.py
zip log_metrics.zip log_metrics.py
```

У результаті в `terraform/lambda/` мають бути 4 файли: `validate.py`,
`validate.zip`, `log_metrics.py`, `log_metrics.zip`.

## 2. Розгортання інфраструктури через Terraform

```bash
cd terraform
terraform init
terraform plan
terraform apply
```

Створює 7 ресурсів:
- IAM-роль для Lambda (`aws_iam_role.lambda_role`) + прикріплена
  керована політика `AWSLambdaBasicExecutionRole`
- дві Lambda-функції (`validate`, `log_metrics`)
- IAM-роль для Step Function (`aws_iam_role.step_function_role`) +
  інлайн-політика, що дозволяє викликати саме ці дві Lambda (принцип
  найменших привілеїв — не `lambda:*`, а конкретні ARN)
- Step Function (`aws_sfn_state_machine.train_pipeline`) зі структурою
  `ValidateData → LogMetrics`

Після `apply` Terraform виводить корисні output-и:
```bash
terraform output state_machine_arn
terraform output start_execution_command
```

## 3. Ручний запуск Step Function

### Через AWS CLI

```bash
aws stepfunctions start-execution \
  --state-machine-arn <ARN з terraform output state_machine_arn> \
  --name "manual-run-$(date +%s)" \
  --input '{"source": "manual", "commit": "local-test"}'
```

### Через AWS Console

1. Відкрити **AWS Console → Step Functions → State machines**.
2. Обрати `mlops-train-automation-pipeline`.
3. Переконатись, що статус — `Active`, а на вкладці **Definition**
   видно граф `Start → ValidateData → LogMetrics → End`.
4. Натиснути **Start execution**, у полі вводу вставити:
   ```json
   {"source": "manual-test", "commit": "test-run-001"}
   ```
5. Підтвердити — на вкладці **Graph view** обидва кроки мають стати
   зеленими (Succeeded), а `Execution status` вгорі — `Succeeded`.

Перевірено вручну: реальний запуск завершився статусом `Succeeded`,
обидва кроки (`ValidateData`, `LogMetrics`) виконались послідовно і
успішно (скріншоти — `screenshots/step-function-definition.png`,
`screenshots/step-function-execution-succeeded.png`).

## 4. GitLab CI

Файл `.gitlab-ci.yml` містить один job — `train-model`, який
автоматично запускає Step Function при кожному push у гілку `main`:

```yaml
train-model:
  stage: train
  image:
    name: amazon/aws-cli:2.15.0
    entrypoint: [""]
  rules:
    - if: '$CI_COMMIT_BRANCH == "main"'
  script:
    - |
      aws stepfunctions start-execution \
        --state-machine-arn "$STATE_MACHINE_ARN" \
        --name "train-$(date +%s)" \
        --input "{\"source\": \"gitlab-ci\", \"commit\": \"$CI_COMMIT_SHORT_SHA\"}"
```

**Як це працює:**
- `image` — офіційний Docker-образ AWS CLI v2.15.0; `entrypoint: [""]`
  скидає стандартний entrypoint образу, щоб GitLab міг виконати наш
  `script` як звичайний shell-скрипт, а не аргумент до `aws`.
- `rules` — job виконується лише для push у `main` (не для кожної
  feature-гілки чи merge request).
- `--state-machine-arn "$STATE_MACHINE_ARN"` — ARN береться зі змінної
  оточення (не захардкоджений у файлі — див. розділ нижче), значення
  можна взяти з `terraform output state_machine_arn`.
- `$CI_COMMIT_SHORT_SHA` — вбудована змінна GitLab з коротким хешем
  коміту, що ініціював пайплайн.

### Необхідні AWS-змінні (GitLab CI/CD Settings → Variables)

| Змінна | Опис |
|---|---|
| `AWS_ACCESS_KEY_ID` | Ключ доступу IAM-користувача з правом `states:StartExecution` на цю state machine |
| `AWS_SECRET_ACCESS_KEY` | Секретний ключ до нього |
| `AWS_DEFAULT_REGION` | Регіон, де розгорнуто Step Function (`us-east-1`) |
| `STATE_MACHINE_ARN` | ARN state machine (з `terraform output state_machine_arn`) |

Усі змінні варто позначити **Masked** (і, за можливості, **Protected**,
якщо job запускається лише для захищених гілок), щоб значення не
потрапляли у відкритому вигляді в лог пайплайну.

Якщо в GitLab-групі/проєкті налаштована **OIDC-інтеграція з AWS**
(GitLab як OIDC-провайдер для `sts:AssumeRoleWithWebIdentity`) —
рекомендується використовувати саме її замість статичних
`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`: тоді job отримує
короткотривалі, автоматично ротовані credentials, а не постійний
секрет, збережений у CI/CD Variables. Конфігурація OIDC виходить за
межі цього README і налаштовується окремо на рівні GitLab-групи/AWS
IAM Identity Provider.

### Приклад JSON, що передається до Step Function

```json
{
  "source": "gitlab-ci",
  "commit": "a1b2c3d"
}
```

Це той самий JSON, який отримує перший крок (`ValidateData`) як
`event`; після виконання `validate.py` повертає його результат (разом
з `status: "valid"`), а `log_metrics.py` отримує вже цей результат як
свій `event` — так дані "перетікають" між кроками Step Function.

## Видалення ресурсів

```bash
cd terraform
terraform destroy
```

Видаляє всі 7 ресурсів (обидві Lambda, обидві IAM-ролі з політиками,
Step Function).