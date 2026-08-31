"""
promote_to_production.py

Промоушен версії моделі зі Staging у Production (окрема дія від тренування,
вимога B2). Стара Production-версія автоматично переводиться в Archived
(зберігає можливість rollback).

Запуск:
    python promote_to_production.py                    # промоутить останню Staging-версію
    python promote_to_production.py --version 4         # промоутить конкретну версію

Змінні оточення:
    MLFLOW_TRACKING_URI     default: http://localhost:5000
    REGISTERED_MODEL_NAME   default: iris-logistic-regression
"""

import argparse
import logging
import os

from mlflow.tracking import MlflowClient

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
REGISTERED_MODEL_NAME = os.getenv("REGISTERED_MODEL_NAME", "iris-logistic-regression")


def get_latest_staging_version(client: MlflowClient) -> str:
    """Повертає версію з найбільшим номером у статусі Staging."""
    versions = client.get_latest_versions(REGISTERED_MODEL_NAME, stages=["Staging"])
    if not versions:
        raise RuntimeError(
            f"Немає жодної версії моделі '{REGISTERED_MODEL_NAME}' у статусі Staging."
        )
    latest = max(versions, key=lambda v: int(v.version))
    return latest.version


def promote(version: str) -> None:
    client = MlflowClient(tracking_uri=MLFLOW_TRACKING_URI)

    # Знаходимо поточну Production-версію (якщо є) — архівуємо її.
    current_prod = client.get_latest_versions(REGISTERED_MODEL_NAME, stages=["Production"])
    for old_version in current_prod:
        logger.info(
            "Архівуємо поточну Production-версію: %s (версія %s)",
            REGISTERED_MODEL_NAME,
            old_version.version,
        )
        client.transition_model_version_stage(
            name=REGISTERED_MODEL_NAME,
            version=old_version.version,
            stage="Archived",
            archive_existing_versions=False,
        )

    # Переводимо нову версію в Production.
    client.transition_model_version_stage(
        name=REGISTERED_MODEL_NAME,
        version=version,
        stage="Production",
        archive_existing_versions=False,
    )
    logger.info(
        "AUDIT: Модель '%s' версія %s переведена в Production", REGISTERED_MODEL_NAME, version
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Промоушен версії моделі в Production")
    parser.add_argument(
        "--version",
        type=str,
        default=None,
        help="Номер версії для промоушену (за замовчуванням — остання Staging-версія)",
    )
    args = parser.parse_args()

    client = MlflowClient(tracking_uri=MLFLOW_TRACKING_URI)
    version = args.version or get_latest_staging_version(client)

    logger.info("Промоутимо версію %s моделі '%s' у Production", version, REGISTERED_MODEL_NAME)
    promote(version)


if __name__ == "__main__":
    main()
