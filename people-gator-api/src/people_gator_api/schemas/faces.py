from __future__ import annotations
from typing import Annotated
import uuid
from pydantic import BaseModel, Field, FiniteFloat, field_validator
from people_gator_api.settings import settings
from people_gator_api.schemas.common import (
    GenericListResponse,
    ListFilterBase,
    ModelEmbedding,
    require_unique_model_embeddings,
    GenericListRequest,
)
from people_gator_api.schemas.face_models import FaceModelStub
from people_gator_api.schemas.missing import MISSING, MissingType, is_missing

# ---------------------------------------------------------------------------
# Face schemas
# ---------------------------------------------------------------------------

NUMBER_OF_FACE_KEYPOINTS = 5
MAX_FACE_BATCH_SIZE = settings.batch.max_face_batch_size

FaceEmbedding = ModelEmbedding[FaceModelStub]


class BoundingBox(BaseModel):
    """Face detection bounding box."""

    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class Keypoint(BaseModel):
    """One keypoint of a face detection."""

    type: str
    x: FiniteFloat
    y: FiniteFloat


class FaceCreateRequest(BaseModel):
    """Request body for ingesting a face detection."""

    identifier: str | MissingType = Field(
        default=MISSING, description="An optional identifier for the face detection."
    )
    bounding_box: BoundingBox = Field(
        description="The bounding box of the face detection."
    )
    keypoints: list[Keypoint] = Field(
        min_length=NUMBER_OF_FACE_KEYPOINTS,
        max_length=NUMBER_OF_FACE_KEYPOINTS,
        description="The keypoints of the face detection. Must contain exactly 5 keypoints.",
    )
    confidence: float = Field(
        ge=0.0, le=1.0, description="The confidence score of the face detection."
    )
    embeddings: list[FaceEmbedding] | MissingType = Field(
        default=MISSING, description="The embeddings of the face detection."
    )
    source_id: uuid.UUID = Field(
        description="The unique identifier of the source from which the face was detected. Mandatory."
    )
    entity_id: uuid.UUID | MissingType = Field(
        default=MISSING,
        description="The unique identifier of the entity associated with the face detection.",
    )

    @field_validator("embeddings")
    @classmethod
    def validate_unique_embeddings(
        cls, embeddings: list[FaceEmbedding]
    ) -> list[FaceEmbedding]:
        require_unique_model_embeddings(embeddings)
        return embeddings


type FacesBatchCreateRequest = Annotated[
    list[FaceCreateRequest], Field(max_length=MAX_FACE_BATCH_SIZE)
]


class FacePatchRequest(BaseModel):
    """Patch body for assigning a face, or unassigning it with a null entity ID."""

    entity_id: uuid.UUID | None | MissingType = Field(
        default=MISSING,
        description="The unique identifier of the entity associated with the face detection. If null, the face will be unassigned from any entity. If MISSING, the entity association will not be modified.",
    )
    embeddings: list[FaceEmbedding] | MissingType = Field(
        default=MISSING,
        description="When provided, upsert each named model vector; unmentioned vectors remain unchanged. An empty list is a no-op.",
    )

    @field_validator("embeddings")
    @classmethod
    def validate_unique_embeddings(
        cls, embeddings: list[FaceEmbedding] | MissingType
    ) -> list[FaceEmbedding] | MissingType:
        if not is_missing(embeddings):
            require_unique_model_embeddings(embeddings)
        return embeddings


class FacePatchBatchItem(FacePatchRequest):
    """Patch body for assigning a face, or unassigning it with a null entity ID in a batch."""

    detection_id: uuid.UUID = Field(
        description="The unique identifier of the face detection."
    )


type FacesBatchPatchRequest = Annotated[
    list[FacePatchBatchItem], Field(max_length=MAX_FACE_BATCH_SIZE)
]


class FaceResponse(BaseModel):
    """A single face detection record."""

    detection_id: uuid.UUID = Field(
        description="The unique identifier of the face detection."
    )
    identifier: str | None = Field(
        default=None, description="An optional identifier for the face detection."
    )
    source_id: uuid.UUID = Field(
        description="The unique identifier of the source from which the face was detected."
    )
    bounding_box: BoundingBox = Field(
        description="The bounding box of the face detection."
    )
    keypoints: list[Keypoint] = Field(
        min_length=NUMBER_OF_FACE_KEYPOINTS,
        max_length=NUMBER_OF_FACE_KEYPOINTS,
        description="The keypoints of the face detection. Must contain exactly 5 keypoints.",
    )
    user_id: uuid.UUID = Field(
        description="The unique identifier of the user who created or owns the face detection."
    )
    entity_id: uuid.UUID | None = Field(
        default=None,
        description="The unique identifier of the entity associated with the face detection.",
    )
    confidence: float = Field(description="The confidence score of the face detection.")
    embeddings: list[str] = Field(
        default_factory=list,
        description="The embedding model identifiers available for the face detection. Embedding vectors are not returned.",
    )


FaceListResponse = GenericListResponse[FaceResponse]


class FaceListFilter(ListFilterBase):
    """Filter criteria for listing faces.
    Every field is optional and can be used to narrow down the results.
    Filter fields are combined using logical AND.
    Lists of criteria in each field are combined using logical OR.
    """

    entity_id: list[uuid.UUID] | MissingType = Field(
        default=MISSING, description="Filter by entity IDs."
    )
    source_id: list[uuid.UUID] | MissingType = Field(
        default=MISSING, description="Filter by source IDs."
    )
    detection_id: list[uuid.UUID] | MissingType = Field(
        default=MISSING, description="Filter by detection IDs."
    )


class FaceListRequest(GenericListRequest):
    """Request body for listing faces with optional filters."""

    filter_: FaceListFilter | MissingType = Field(
        default=MISSING, description="The filter criteria to select faces."
    )


__all__ = [
    "MAX_FACE_BATCH_SIZE",
    "FaceEmbedding",
    "BoundingBox",
    "Keypoint",
    "FaceCreateRequest",
    "FacesBatchCreateRequest",
    "FacePatchRequest",
    "FacePatchBatchItem",
    "FacesBatchPatchRequest",
    "FaceResponse",
    "FaceListResponse",
    "FaceListFilter",
    "FaceListRequest",
]
