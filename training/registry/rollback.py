"""
rollback.py

Rollback: повертає останню Archived-версію моделі назад у Production.
Одна команда — вимога B4.

Запуск:
    python rollback.py

Змінні оточення:
    MLFLOW_TRACKING_URI     default: http://localhost:5000
    REGISTERED_MODEL_NAME   default: iris-logistic-regression
"""

import logging
import os

from mlflow.tracking import MlflowClient

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
REGISTERED_MODEL_NAME = os.getenv("REGISTERED_MODEL_NAME", "iris-logistic-regression")


def main() -> None:
    client = MlflowClient(tracking_uri=MLFLOW_TRACKING_URI)

    archived = client.get_latest_versions(REGISTERED_MODEL_NAME, stages=["Archived"])
    if not archived:
        raise RuntimeError(
            f"Немає жодної Archived-версії моделі '{REGISTERED_MODEL_NAME}' для rollback."
        )
    rollback_target = max(archived, key=lambda v: int(v.version))

    current_prod = client.get_latest_versions(REGISTERED_MODEL_NAME, stages=["Production"])
    for old_version in current_prod:
        logger.info(
            "AUDIT: Знімаємо з Production версію %s (переходить у Archived через rollback)",
            old_version.version,
        )
        client.transition_model_version_stage(
            name=REGISTERED_MODEL_NAME,
            version=old_version.version,
            stage="Archived",
            archive_existing_versions=False,
        )

    client.transition_model_version_stage(
        name=REGISTERED_MODEL_NAME,
        version=rollback_target.version,
        stage="Production",
        archive_existing_versions=False,
    )
    logger.info(
        "AUDIT: ROLLBACK виконано. Версія %s знову в Production", rollback_target.version
    )


if __name__ == "__main__":
    main()
