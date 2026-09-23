"""Schemas for the administratively managed face embedding model registry."""

from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints


type FaceModelStub = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=255),
]


class FaceModelRegisterRequest(BaseModel):
    """Register one model before storing or searching its face vectors."""

    model_stub: FaceModelStub = Field(
        description="Stable identifier stored with each embedding.",
    )
    embedding_dim: int = Field(
        gt=0,
        description="Number of elements in every vector produced by the model.",
    )


class FaceModelResponse(BaseModel):
    model_stub: FaceModelStub
    embedding_dim: int


class FaceModelListResponse(BaseModel):
    items: list[FaceModelResponse]


__all__ = [
    "FaceModelListResponse",
    "FaceModelRegisterRequest",
    "FaceModelResponse",
    "FaceModelStub",
]
