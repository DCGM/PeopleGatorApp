"""Pydantic schemas for search and search endpoints."""

from typing import Self
import uuid
from pydantic import (
    BaseModel,
    Field,
    FiniteFloat,
    model_validator,
)
from people_gator_api.schemas.entities import EntityListFilter, EntityResponse
from people_gator_api.schemas.common import GenericListRequest, GenericListResponse
from people_gator_api.schemas.enums import (
    DEFAULT_FACE_EMBEDDING_MODEL,
    FaceEmbeddingModel,
    ScoreAggregation,
    ScoreFusion
)
from people_gator_api.schemas.faces import FaceListFilter, FaceResponse
from people_gator_api.schemas.missing import MISSING, MissingType
from people_gator_api.schemas.sources import DocumentListFilter, DocumentResponse, PageListFilter, PageResponse

# Reciprocal-rank fusion uses one-based ranks and equal modality weights.
RRF_K = 60

# ---------------------------------------------------------------------------
# Base classes for search results and queries
# ---------------------------------------------------------------------------


class FoundItemBase(BaseModel):
    """Search scores use higher-is-better semantics."""

    text_score: FiniteFloat | None = Field(
        default=None,
        description=(
            "Aggregated text relevance, or None when text was not requested."
        ),
    )
    face_score: FiniteFloat | None = Field(
        default=None,
        description=(
            "Aggregated cosine similarity, or None when faces were not requested."
        ),
    )
    score: FiniteFloat = Field(
        gt=0,
        description=(
            "Final reciprocal-rank-fusion score. Higher values rank first."
        )
    )


class QueryBase(BaseModel):
    """Base class for search queries."""
    text: list[str] | MissingType = Field(
        default=MISSING,
        description="Unique, non-blank text queries. Candidate scores are aggregated across them.",
    )
    face_id: list[uuid.UUID] | MissingType = Field(
        default=MISSING,
        description="Unique reference face IDs. Every ID must exist and contain the selected embedding model.",
    )
    face_embedding_model: FaceEmbeddingModel = Field(
        default=DEFAULT_FACE_EMBEDDING_MODEL,
        description="The face embedding model used for the search.",
    )
    exclude_reference_face_id: bool = Field(
        default=True,
        description="Whether to exclude the reference face ID from the search results.",
    )
    score_aggregation: ScoreAggregation = Field(
        default=ScoreAggregation.min,
        description="How higher-is-better candidate scores within each modality are aggregated across query items.",
    )
    score_fusion: ScoreFusion = Field(
        default=ScoreFusion.rrf,
        description="How independently ranked modality result lists are fused.",
    )

    @model_validator(mode="after")
    def validate_modalities(self) -> Self:
        text_values = self.text if isinstance(self.text, list) else []
        face_ids = self.face_id if isinstance(self.face_id, list) else []
        if not text_values and not face_ids:
            raise ValueError(
                "provide at least one non-empty search modality: text or face_id"
            )

        if any(not value.strip() for value in text_values):
            raise ValueError("text queries must not be blank")
        if len(text_values) != len(set(text_values)):
            raise ValueError("text queries must be unique")
        if len(face_ids) != len(set(face_ids)):
            raise ValueError("face_id values must be unique")
        return self


class GenericSearchRequest[F: BaseModel](GenericListRequest):
    """Backend-neutral multimodal search request.

    Each modality ranks candidates independently after score aggregation. RRF
    uses one-based ranks, RRF_K, and equal modality weight. Results order by
    final score descending and object UUID ascending. With one modality, the
    final score contains one RRF term.
    Raw text relevance is backend-native; the contract standardizes score direction,
    aggregation, fusion, and deterministic tie-breaking, not identical raw values.
    """

    query: QueryBase = Field(
        ...,
        description="The search query containing text and face IDs.",
    )
    filter: F | None = Field(
        default=None,
        description="Optional filter to apply to the search results.",
    )


# ---------------------------------------------------------------------------
# Entity search result type
# ---------------------------------------------------------------------------


class FoundEntity(EntityResponse, FoundItemBase):
    """A single result from a nearest-neighbour search over an annotation collection."""


"""List response for entity search results."""
SearchEntitiesResultListResponse = GenericListResponse[FoundEntity]


"""Request type for entity search."""
SearchEntitiesRequest = GenericSearchRequest[EntityListFilter]


# ---------------------------------------------------------------------------
# Face similarity search
# ---------------------------------------------------------------------------

class FoundFace(FaceResponse, FoundItemBase):
    """A single result from a nearest-neighbour search over a face collection."""


"""List response for face similarity search results."""
SearchFacesResultListResponse = GenericListResponse[FoundFace]


"""Request type for face similarity search."""
SearchFacesRequest = GenericSearchRequest[FaceListFilter]

# ---------------------------------------------------------------------------
# Page similarity search
# ---------------------------------------------------------------------------


class FoundPage(PageResponse, FoundItemBase):
    """A single result from a nearest-neighbour search over a page collection."""


"""List response for page similarity search results."""
SearchPagesResultListResponse = GenericListResponse[FoundPage]


"""Request type for page similarity search."""
SearchPagesRequest = GenericSearchRequest[PageListFilter]


# ---------------------------------------------------------------------------
# Document similarity search
# ---------------------------------------------------------------------------


class FoundDocument(DocumentResponse, FoundItemBase):
    """A single result from a nearest-neighbour search over a document collection."""

"""List response for document similarity search results."""
SearchDocumentsResultListResponse = GenericListResponse[FoundDocument]


"""Request type for document similarity search."""
SearchDocumentsRequest = GenericSearchRequest[DocumentListFilter]


__all__ = [
    "FoundItemBase",
    "RRF_K",
    "QueryBase",
    "GenericSearchRequest",
    "FoundEntity",
    "SearchEntitiesResultListResponse",
    "SearchEntitiesRequest",
    "FoundFace",
    "SearchFacesResultListResponse",
    "SearchFacesRequest",
    "FoundPage",
    "SearchPagesResultListResponse",
    "SearchPagesRequest",
    "FoundDocument",
    "SearchDocumentsResultListResponse",
    "SearchDocumentsRequest",
]
