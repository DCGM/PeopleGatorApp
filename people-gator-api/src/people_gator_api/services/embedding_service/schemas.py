from pydantic import (
    BaseModel,
)


class DetectionResult(BaseModel):
    class_id: int
    confidence: float
    image_width: int
    image_height: int
    x_min: float
    y_min: float
    x_max: float
    y_max: float
    keypoints: list[tuple[float, float, float]] | None = None
    embedding: list[float] | None = None


class AllFacesResult(BaseModel):
    faces: list[DetectionResult]


class TimmImageEmbeddingResponse(BaseModel):
    embedding: list[float]


class TextEmbeddingResponse(BaseModel):
    embedding: list[float]
