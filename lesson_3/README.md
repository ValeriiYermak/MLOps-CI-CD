# ДЗ №3: Контейнеризація ML-моделі (PyTorch + Docker)

Проєкт демонструє підготовку середовища, експорт PyTorch-моделі у TorchScript
та побудову двох Docker-образів (fat і оптимізований slim) для inference.

## Вимоги

- Docker Desktop (з Docker Compose V2, `docker compose version`)
- Python 3.13+
- pip
- Git Bash або сумісний bash-термінал (для запуску `install_dev_tools.sh`)

## Структура проєкту

lesson_3/
├── app/
│ └── inference.py # inference-скрипт
├── model/
│ └── model.pt # TorchScript-модель (створюється export_model.py)
├── scripts/
│ └── install_dev_tools.sh
├── export_model.py
├── requirements.txt
├── Dockerfile.fat
├── Dockerfile.slim
├── .dockerignore
├── example.jpg
├── report.md
└── README.md

## Джерело example.jpg

Тестове зображення собаки, офіційно використовується PyTorch у власних
туторіалах з класифікації зображень:
https://github.com/pytorch/hub/raw/master/images/dog.jpg

## Кроки запуску

### 1. Перевірка та підготовка середовища

```bash
chmod +x scripts/install_dev_tools.sh
bash scripts/install_dev_tools.sh
```

Скрипт перевіряє наявність Docker, Docker Compose V2, Python 3.13+, pip
та ML-залежностей (torch, torchvision, pillow); за потреби встановлює
відсутні Python-пакети з `requirements.txt`. Ідемпотентний — повторний
запуск не дублює дій. Лог зберігається в `install.log`.

### 2. Експорт моделі в TorchScript

```bash
python3 export_model.py
```

Завантажує попередньо натреновану MobileNetV2 (`torchvision.models`),
переводить у режим `eval()` і зберігає через `torch.jit.trace`
у `model/model.pt` (~14 MB).

### 3. Локальний inference (без Docker)

```bash
python3 app/inference.py example.jpg
```

Приклад результату:

Top-3 передбачення для 'example.jpg':

1. class_id=258, confidence=0.3091
2. class_id=259, confidence=0.0510
3. class_id=261, confidence=0.0159

### 4. Збірка Docker-образів

```bash
docker build -f Dockerfile.fat -t ml-infer-fat:1.0 .
docker build -f Dockerfile.slim -t ml-infer-slim:1.0 .
```

> **Примітка:** обидва Dockerfile явно вказують CPU-only індекс PyTorch
> (`--index-url https://download.pytorch.org/whl/cpu`), щоб уникнути
> завантаження важких CUDA/GPU-залежностей всередині Linux-контейнера
> (стандартний PyPI-індекс за замовчуванням віддає GPU-версію torch).

### 5. Запуск inference в Docker

```bash
docker run --rm -v ${PWD}/example.jpg:/app/example.jpg ml-infer-fat:1.0
docker run --rm -v ${PWD}/example.jpg:/app/example.jpg ml-infer-slim:1.0
```

Обидва контейнери повертають ідентичний результат (див. `report.md`).

### 6. Порівняння образів

```bash
docker images | grep ml-infer
docker history ml-infer-fat:1.0
docker history ml-infer-slim:1.0
```

Детальний аналіз розмірів, шарів і пропозиції з оптимізації — у `report.md`.

## Різниця fat vs slim (коротко)

| | Fat | Slim |
|---|---|---|
| Базовий образ | `python:3.13` | `python:3.13-slim` |
| Multi-stage build | Ні | Так (builder + runtime) |
| Розмір | 2.85 GB | 1.4 GB |
| Inference результат | ідентичний slim | ідентичний fat |

Повний аналіз — у [`report.md`](./report.md).


