"""
train_and_push.py

Тренує кілька моделей LogisticRegression на датасеті Iris з різними
гіперпараметрами (C, max_iter), логує кожен запуск у MLflow (параметри,
метрики, модель-артефакт), реєструє модель у MLflow Model Registry
(нова версія на кожен run, автоматичний перехід у Staging), пушить
accuracy/loss у Prometheus PushGateway з міткою run_id, і в кінці
копіює модель із найкращою accuracy у локальну директорію ./best_model/.

Запуск:
    python train_and_push.py

Змінні оточення (усі опційні, значення за замовчуванням розраховані на
запуск через kubectl port-forward до сервісів у кластері):

    MLFLOW_TRACKING_URI     default: http://localhost:5000
    PUSHGATEWAY_URL         default: localhost:9091
    MLFLOW_EXPERIMENT       default: iris-logistic-regression
    REGISTERED_MODEL_NAME   default: iris-logistic-regression
    BEST_MODEL_DIR          default: best_model
    GIT_COMMIT_SHA          default: визначається автоматично через `git rev-parse --short HEAD`

    # Дані для підключення MLflow-клієнта (boto3) до MinIO як до S3.
    AWS_ACCESS_KEY_ID       default: minioadmin
    AWS_SECRET_ACCESS_KEY   default: minioadmin123
    MLFLOW_S3_ENDPOINT_URL  default: http://localhost:9000
"""

import hashlib
import logging
import os
import shutil
import subprocess

import mlflow
import mlflow.sklearn
from mlflow.tracking import MlflowClient
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
REGISTERED_MODEL_NAME = os.getenv("REGISTERED_MODEL_NAME", "iris-logistic-regression")
BEST_MODEL_DIR = os.getenv("BEST_MODEL_DIR", "best_model")

# --- Сітка гіперпараметрів для перебору ---
PARAM_GRID = [
    {"C": 0.01, "max_iter": 100},
    {"C": 0.1, "max_iter": 100},
    {"C": 1.0, "max_iter": 200},
    {"C": 10.0, "max_iter": 200},
    {"C": 100.0, "max_iter": 300},
]


def get_git_commit_sha() -> str:
    """Повертає короткий Git SHA поточного коміту (для трасованості моделі)."""
    override = os.getenv("GIT_COMMIT_SHA")
    if override:
        return override
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Не вдалось визначити Git SHA: %s", exc)
        return "unknown"


def get_dataset_hash(X, y) -> str:
    """SHA256-хеш датасету — версія даних для трасованості (reference для drift-аналізу)."""
    hasher = hashlib.sha256()
    hasher.update(X.tobytes())
    hasher.update(y.tobytes())
    return hasher.hexdigest()[:12]


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
    client = MlflowClient()

    logger.info("MLflow tracking URI: %s", MLFLOW_TRACKING_URI)
    logger.info("Експеримент: %s", EXPERIMENT_NAME)

    git_sha = get_git_commit_sha()
    logger.info("Git commit SHA: %s", git_sha)

    X, y = load_iris(return_X_y=True)
    dataset_hash = get_dataset_hash(X, y)
    logger.info("Dataset hash (SHA256, скорочено): %s", dataset_hash)

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
            mlflow.log_param("git_commit_sha", git_sha)
            mlflow.log_param("dataset_hash", dataset_hash)
            mlflow.log_metric("accuracy", accuracy)
            mlflow.log_metric("loss", loss)

            model_info = mlflow.sklearn.log_model(
                model,
                artifact_path="model",
                registered_model_name=REGISTERED_MODEL_NAME,
            )

            # Кожен новий run реєструє нову версію моделі — переводимо її
            # автоматично у Staging (вимога B2: нова версія завжди Staging).
            registered_version = model_info.registered_model_version
            client.transition_model_version_stage(
                name=REGISTERED_MODEL_NAME,
                version=registered_version,
                stage="Staging",
                archive_existing_versions=False,
            )
            logger.info(
                "Модель %s версія %s зареєстрована та переведена в Staging",
                REGISTERED_MODEL_NAME,
                registered_version,
            )

            push_metrics_to_gateway(run_id, accuracy, loss)

            logger.info(
                "Run %s завершено: accuracy=%.4f loss=%.4f", run_id, accuracy, loss
            )
            results.append(
                {
                    "run_id": run_id,
                    "accuracy": accuracy,
                    "loss": loss,
                    "model_version": registered_version,
                }
            )

    best = max(results, key=lambda r: r["accuracy"])
    logger.info(
        "Найкращий run: %s (accuracy=%.4f, model version=%s)",
        best["run_id"],
        best["accuracy"],
        best["model_version"],
    )

    copy_best_model(best["run_id"])


if __name__ == "__main__":
    main()
