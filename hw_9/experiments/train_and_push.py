"""
train_and_push.py

Тренує кілька моделей LogisticRegression на датасеті Iris з різними
гіперпараметрами (C, max_iter), логує кожен запуск у MLflow (параметри,
метрики, модель-артефакт), пушить accuracy/loss у Prometheus PushGateway
з міткою run_id, і в кінці копіює модель із найкращою accuracy у
локальну директорію ./best_model/.

Запуск:
    python train_and_push.py

Змінні оточення (усі опційні, значення за замовчуванням розраховані на
запуск через kubectl port-forward до сервісів у кластері):

    MLFLOW_TRACKING_URI     default: http://localhost:5000
    PUSHGATEWAY_URL         default: localhost:9091
    MLFLOW_EXPERIMENT       default: iris-logistic-regression
    BEST_MODEL_DIR          default: best_model

    # Дані для підключення MLflow-клієнта (boto3) до MinIO як до S3.
    # За замовчуванням підставляються ті самі облікові дані, що й у
    # argocd/applications/minio.yaml — якщо в minio.yaml їх змінили,
    # треба або поправити тут, або передати через змінні оточення.
    AWS_ACCESS_KEY_ID       default: minioadmin
    AWS_SECRET_ACCESS_KEY   default: minioadmin123
    MLFLOW_S3_ENDPOINT_URL  default: http://localhost:9000
"""

import logging
import os
import shutil

import mlflow
import mlflow.sklearn
from prometheus_client import CollectorRegistry, Gauge, push_to_gateway
from sklearn.datasets import load_iris
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, log_loss
from sklearn.model_selection import train_test_split

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# --- Налаштування підключення (з дефолтами для port-forward) ---
os.environ.setdefault("AWS_ACCESS_KEY_ID", "minioadmin")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "minioadmin123")
os.environ.setdefault("MLFLOW_S3_ENDPOINT_URL", "http://localhost:9000")

MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
PUSHGATEWAY_URL = os.getenv("PUSHGATEWAY_URL", "localhost:9091")
EXPERIMENT_NAME = os.getenv("MLFLOW_EXPERIMENT", "iris-logistic-regression")
BEST_MODEL_DIR = os.getenv("BEST_MODEL_DIR", "best_model")

# --- Сітка гіперпараметрів для перебору ---
PARAM_GRID = [
    {"C": 0.01, "max_iter": 100},
    {"C": 0.1, "max_iter": 100},
    {"C": 1.0, "max_iter": 200},
    {"C": 10.0, "max_iter": 200},
    {"C": 100.0, "max_iter": 300},
]


def push_metrics_to_gateway(run_id: str, accuracy: float, loss: float) -> None:
    """Пушить accuracy та loss конкретного run-у в Prometheus PushGateway."""
    registry = CollectorRegistry()
    accuracy_gauge = Gauge(
        "mlflow_accuracy",
        "Accuracy тренованої моделі",
        ["run_id"],
        registry=registry,
    )
    loss_gauge = Gauge(
        "mlflow_loss",
        "Log loss тренованої моделі",
        ["run_id"],
        registry=registry,
    )
    accuracy_gauge.labels(run_id=run_id).set(accuracy)
    loss_gauge.labels(run_id=run_id).set(loss)

    try:
        push_to_gateway(PUSHGATEWAY_URL, job="mlflow_training", registry=registry)
        logger.info(
            "Метрики run %s запушено в PushGateway (%s)", run_id, PUSHGATEWAY_URL
        )
    except Exception as exc:  # noqa: BLE001
        # Не зупиняємо весь тренувальний цикл через збій пушу метрик —
        # логуємо попередження і продовжуємо роботу з рештою run-ів.
        logger.warning("Не вдалось запушити метрики в PushGateway: %s", exc)


def copy_best_model(run_id: str) -> None:
    """Скачує модель-артефакт найкращого run-у в ./best_model/."""
    if os.path.exists(BEST_MODEL_DIR):
        shutil.rmtree(BEST_MODEL_DIR)

    local_path = mlflow.artifacts.download_artifacts(
        run_id=run_id, artifact_path="model", dst_path="."
    )
    shutil.move(local_path, BEST_MODEL_DIR)
    logger.info("Найкращу модель скопійовано в %s", BEST_MODEL_DIR)


def main() -> None:
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment(EXPERIMENT_NAME)

    logger.info("MLflow tracking URI: %s", MLFLOW_TRACKING_URI)
    logger.info("Експеримент: %s", EXPERIMENT_NAME)

    X, y = load_iris(return_X_y=True)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    results = []

    for params in PARAM_GRID:
        with mlflow.start_run() as run:
            run_id = run.info.run_id
            logger.info("Запуск run %s з параметрами %s", run_id, params)

            model = LogisticRegression(**params)
            model.fit(X_train, y_train)

            y_pred = model.predict(X_test)
            y_proba = model.predict_proba(X_test)

            accuracy = accuracy_score(y_test, y_pred)
            loss = log_loss(y_test, y_proba)

            mlflow.log_params(params)
            mlflow.log_metric("accuracy", accuracy)
            mlflow.log_metric("loss", loss)
            mlflow.sklearn.log_model(model, artifact_path="model")

            push_metrics_to_gateway(run_id, accuracy, loss)

            logger.info(
                "Run %s завершено: accuracy=%.4f loss=%.4f", run_id, accuracy, loss
            )
            results.append({"run_id": run_id, "accuracy": accuracy, "loss": loss})

    best = max(results, key=lambda r: r["accuracy"])
    logger.info(
        "Найкращий run: %s (accuracy=%.4f)", best["run_id"], best["accuracy"]
    )

    copy_best_model(best["run_id"])


if __name__ == "__main__":
    main()