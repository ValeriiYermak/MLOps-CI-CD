import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.model_loader import (
    CLASS_NAMES,
    ModelLoadError,
    get_current_production_version,
    load_production_model,
)
from app.schemas import HealthResponse, IrisFeatures, PredictionResponse

logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}',
)
logger = logging.getLogger("inference")

REQUEST_COUNT = Counter(
    "inference_requests_total", "Кількість запитів", ["method", "endpoint", "status"]
)
REQUEST_LATENCY = Histogram(
    "inference_request_latency_seconds",
    "Латентність запитів",
    ["endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)
ERROR_COUNT = Counter(
    "inference_errors_total", "Кількість помилок", ["endpoint", "error_type"]
)

MODEL_RELOAD_INTERVAL_SECONDS = 30

limiter = Limiter(key_func=get_remote_address)

model_state = {"model": None, "version": None}


def _try_load_model() -> None:
    try:
        model, version = load_production_model()
        model_state["model"] = model
        model_state["version"] = version
        logger.info('{"event":"model_loaded","version":"%s"}', version)
    except ModelLoadError as exc:
        logger.error('{"event":"model_load_failed","error":"%s"}', str(exc))


async def _model_watcher() -> None:
    """
    Фоновий таск: раз на MODEL_RELOAD_INTERVAL_SECONDS перевіряє номер
    поточної Production-версії в Registry. Якщо вона відрізняється від
    завантаженої (або модель ще не завантажена) — перезавантажує модель
    у пам'яті поду, без рестарту контейнера. Це закриває розрив між
    "модель промоутнули" і "inference реально почав її використовувати" —
    без потреби вручну видаляти под після кожного promote/rollback.
    """
    while True:
        try:
            current_version = get_current_production_version()
            if current_version and current_version != model_state["version"]:
                logger.info(
                    '{"event":"new_production_version_detected","version":"%s"}',
                    current_version,
                )
                _try_load_model()
        except Exception as exc:  # noqa: BLE001
            logger.warning('{"event":"model_watcher_check_failed","error":"%s"}', str(exc))
        await asyncio.sleep(MODEL_RELOAD_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _try_load_model()
    watcher_task = asyncio.create_task(_model_watcher())
    yield
    watcher_task.cancel()


app = FastAPI(title="Iris Inference Service", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    ERROR_COUNT.labels(endpoint=request.url.path, error_type="validation_error").inc()
    fields = [".".join(str(p) for p in err["loc"][1:]) for err in exc.errors()]
    return JSONResponse(
        status_code=400,
        content={"error": "invalid_input", "invalid_fields": fields},
    )


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start = time.time()
    endpoint = request.url.path
    try:
        response = await call_next(request)
    except Exception:
        ERROR_COUNT.labels(endpoint=endpoint, error_type="unhandled_exception").inc()
        raise
    duration = time.time() - start
    REQUEST_LATENCY.labels(endpoint=endpoint).observe(duration)
    REQUEST_COUNT.labels(
        method=request.method, endpoint=endpoint, status=response.status_code
    ).inc()
    return response


@app.get("/health", response_model=HealthResponse)
async def health():
    if model_state["model"] is None:
        return HealthResponse(status="no_model_loaded")
    return HealthResponse(
        status="ok", model_version=model_state["version"], model_stage="Production"
    )


@app.get("/metrics")
async def metrics():
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/predict", response_model=PredictionResponse)
@limiter.limit("30/minute")
async def predict(request: Request, features: IrisFeatures):
    if model_state["model"] is None:
        ERROR_COUNT.labels(endpoint="/predict", error_type="model_not_loaded").inc()
        return JSONResponse(
            status_code=503, content={"error": "model_not_available"}
        )

    row = [[
        features.sepal_length,
        features.sepal_width,
        features.petal_length,
        features.petal_width,
    ]]

    proba = model_state["model"]._model_impl.predict_proba(row)[0]
    predicted_class = int(proba.argmax())

    logger.info(
        '{"event":"prediction","model_version":"%s","predicted_class":%d}',
        model_state["version"],
        predicted_class,
    )

    return PredictionResponse(
        predicted_class=predicted_class,
        class_name=CLASS_NAMES[predicted_class],
        probabilities={CLASS_NAMES[i]: float(p) for i, p in enumerate(proba)},
        model_version=model_state["version"],
    )
