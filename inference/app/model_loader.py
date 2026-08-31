import hashlib
import logging
import os
import tempfile

import mlflow.pyfunc
from mlflow.tracking import MlflowClient

logger = logging.getLogger(__name__)

MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow.mlops-system.svc.cluster.local:5000")
REGISTERED_MODEL_NAME = os.getenv("REGISTERED_MODEL_NAME", "iris-logistic-regression")

CLASS_NAMES = {0: "setosa", 1: "versicolor", 2: "virginica"}


class ModelLoadError(Exception):
    """Піднімається, коли модель не вдалось завантажити або checksum не збігся."""


def _compute_checksum(local_path: str) -> str:
    hasher = hashlib.sha256()
    for root, _, files in os.walk(local_path):
        for fname in sorted(files):
            fpath = os.path.join(root, fname)
            with open(fpath, "rb") as f:
                hasher.update(f.read())
    return hasher.hexdigest()


def get_current_production_version() -> str | None:
    """
    Легкий опитувальний запит — лише дізнатись НОМЕР поточної Production-версії,
    без завантаження самої моделі. Використовується фоновим поллінгом, щоб
    виявити, що з'явилась нова Production-версія (напр. після promote/rollback),
    не перевантажуючи Registry повним download на кожен цикл перевірки.
    """
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    client = MlflowClient()
    versions = client.get_latest_versions(REGISTERED_MODEL_NAME, stages=["Production"])
    if not versions:
        return None
    return versions[0].version


def load_production_model():
    """
    Завантажує модель зі стадії Production. Перед завантаженням у пам'ять
    звіряє SHA256-checksum скачаного артефакту з тегом, записаним при
    тренуванні (C4 — immutable model artifacts). Якщо checksum не
    збігається — модель вважається скомпрометованою, завантаження
    відхиляється.
    """
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    client = MlflowClient()

    versions = client.get_latest_versions(REGISTERED_MODEL_NAME, stages=["Production"])
    if not versions:
        raise ModelLoadError(
            f"Немає жодної версії моделі '{REGISTERED_MODEL_NAME}' у стадії Production."
        )
    version_info = versions[0]
    version = version_info.version
    run_id = version_info.run_id

    expected_checksum = client.get_model_version(REGISTERED_MODEL_NAME, version).tags.get(
        "sha256_checksum"
    )
    if not expected_checksum:
        raise ModelLoadError(
            f"Версія {version} не має tag sha256_checksum — неможливо перевірити цілісність."
        )

    with tempfile.TemporaryDirectory() as tmp_dir:
        local_path = mlflow.artifacts.download_artifacts(
            run_id=run_id, artifact_path="model", dst_path=tmp_dir
        )
        actual_checksum = _compute_checksum(local_path)

        if actual_checksum != expected_checksum:
            raise ModelLoadError(
                f"Checksum моделі версії {version} НЕ збігається! "
                f"Очікувалось {expected_checksum}, отримано {actual_checksum}. "
                "Завантаження відхилено — можлива компрометація артефакту."
            )

        logger.info("Checksum версії %s підтверджено: %s", version, actual_checksum)
        model = mlflow.pyfunc.load_model(local_path)

    return model, version
