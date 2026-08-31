from pydantic import BaseModel, Field


class IrisFeatures(BaseModel):
    """Вхідна схема для /predict — 4 виміри квітки Iris (у сантиметрах)."""

    sepal_length: float = Field(..., gt=0, le=15, description="Довжина чашолистка, см")
    sepal_width: float = Field(..., gt=0, le=15, description="Ширина чашолистка, см")
    petal_length: float = Field(..., gt=0, le=15, description="Довжина пелюстки, см")
    petal_width: float = Field(..., gt=0, le=15, description="Ширина пелюстки, см")

    model_config = {
        "json_schema_extra": {
            "example": {
                "sepal_length": 5.1,
                "sepal_width": 3.5,
                "petal_length": 1.4,
                "petal_width": 0.2,
            }
        }
    }


class PredictionResponse(BaseModel):
    predicted_class: int
    class_name: str
    probabilities: dict[str, float]
    model_version: str


class HealthResponse(BaseModel):
    status: str
    model_version: str | None = None
    model_stage: str | None = None
