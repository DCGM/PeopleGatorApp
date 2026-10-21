"""Pydantic schemas for search and search endpoints."""

from enum import StrEnum
from typing import Self
import uuid
from pydantic import (
    BaseModel,
    Field,
    FiniteFloat,
    model_validator,
    field_validator,
)
from people_gator_api.schemas.entities import EntityListFilter, EntityResponse
from people_gator_api.schemas.common import GenericListRequest, GenericListResponse
from people_gator_api.schemas.sorting import (
    DocumentSortField,
    EntitySortField,
    FaceSortField,
    PageSortField,
    SortableRequest,
)
from people_gator_api.schemas.enums import (
    DEFAULT_FACE_EMBEDDING_MODEL,
    ScoreAggregation,
    ScoreFusion,
)
from people_gator_api.schemas.faces import FaceListFilter, FaceResponse
from people_gator_api.schemas.face_models import FaceModelStub
from people_gator_api.schemas.missing import MISSING, MissingType
from people_gator_api.schemas.sources import (
    DocumentListFilter,
    DocumentResponse,
    PageListFilter,
    PageResponse,
)

# Reciprocal-rank fusion uses one-based ranks and equal modality weights.
RRF_K = 60

# ---------------------------------------------------------------------------
# Base classes for search results and queries
# ---------------------------------------------------------------------------


class FoundItemBase(BaseModel):
    """Search scores use higher-is-better semantics."""

    text_score: FiniteFloat | None = Field(
        default=None,
        description=("Aggregated text relevance, or None when text was not requested."),
    )
    face_score: FiniteFloat | None = Field(
        default=None,
        description=(
            "Aggregated cosine similarity, or None when faces were not requested."
        ),
    )
    score: FiniteFloat = Field(
        gt=0,
        description=("Final reciprocal-rank-fusion score. Higher values rank first."),
    )


class QueryBase(BaseModel):
    """Base class for search queries."""

    text: list[str] | MissingType = Field(
        default=MISSING,
        description="Unique, non-blank text queries. Candidate scores are aggregated across them.",
    )
    face_id: list[uuid.UUID] | MissingType = Field(
        default=MISSING,
        description="Unique reference face IDs. Every ID must exist and contain a finite, nonzero embedding for the selected model.",
    )
    face_embedding_model: FaceModelStub = Field(
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
        if not text_values and not face_ids and not self.has_entity_reference():
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

    def has_entity_reference(self) -> bool:
        return False


class EntityAnnotation(StrEnum):
    faces = "faces"
    aliases = "aliases"
    name = "name"


class EntitySearchQuery(QueryBase):
    """Entity reference inputs are supported only by face and entity search."""

    entity_id: uuid.UUID | None = Field(
        default=None,
        description="Resolve stored reference inputs from this entity. Independent of filter.entity_id. Unknown entities or no usable combined inputs produce 422 invalid_search.",
    )
    entity_annotations: list[EntityAnnotation] = Field(
        default_factory=lambda: list(EntityAnnotation),
        min_length=1,
        description="Reference inputs: faces, aliases, name, or any combination. Omitted means all three. Derived inputs are combined with explicit text/face inputs; incompatible entity faces are skipped.",
    )

    @field_validator("entity_annotations")
    @classmethod
    def canonical_annotations(
        cls, values: list[EntityAnnotation]
    ) -> list[EntityAnnotation]:
        return [annotation for annotation in EntityAnnotation if annotation in values]

    def has_entity_reference(self) -> bool:
        return self.entity_id is not None

    @model_validator(mode="after")
    def validate_entity_annotations(self) -> Self:
        if self.entity_id is None and "entity_annotations" in self.model_fields_set:
            raise ValueError("entity_annotations requires entity_id")
        return self


class GenericSearchRequest[F: BaseModel, S: StrEnum](
    GenericListRequest, SortableRequest[S]
):
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
    filter_: F | None = Field(
        default=None,
        description="Optional filter to apply to the search results.",
    )

    @classmethod
    def is_search(cls) -> bool:
        return True


# ---------------------------------------------------------------------------
# Entity search result type
# ---------------------------------------------------------------------------


class FoundEntity(EntityResponse, FoundItemBase):
    matched_detection_ids: list[uuid.UUID] = Field(
        default_factory=list,
        description="Actual face-similarity witnesses for this result; never an arbitrary portrait.",
    )
    """A single result from a nearest-neighbour search over an annotation collection."""


"""List response for entity search results."""
SearchEntitiesResultListResponse = GenericListResponse[FoundEntity]


"""Request type for entity search."""


class SearchEntitiesRequest(GenericSearchRequest[EntityListFilter, EntitySortField]):
    query: EntitySearchQuery

    @field_validator("query", mode="before")
    @classmethod
    def accept_explicit_query(cls, value):
        return (
            value.model_dump()
            if isinstance(value, QueryBase) and not isinstance(value, EntitySearchQuery)
            else value
        )


# ---------------------------------------------------------------------------
# Face similarity search
# ---------------------------------------------------------------------------


class FoundFace(FaceResponse, FoundItemBase):
    """A single result from a nearest-neighbour search over a face collection."""


"""List response for face similarity search results."""
SearchFacesResultListResponse = GenericListResponse[FoundFace]


"""Request type for face similarity search."""


class SearchFacesRequest(GenericSearchRequest[FaceListFilter, FaceSortField]):
    query: EntitySearchQuery

    @field_validator("query", mode="before")
    @classmethod
    def accept_explicit_query(cls, value):
        return (
            value.model_dump()
            if isinstance(value, QueryBase) and not isinstance(value, EntitySearchQuery)
            else value
        )


# ---------------------------------------------------------------------------
# Page similarity search
# ---------------------------------------------------------------------------


class FoundPage(PageResponse, FoundItemBase):
    """A single result from a nearest-neighbour search over a page collection."""


"""List response for page similarity search results."""
SearchPagesResultListResponse = GenericListResponse[FoundPage]


"""Request type for page similarity search."""
SearchPagesRequest = GenericSearchRequest[PageListFilter, PageSortField]


# ---------------------------------------------------------------------------
# Document similarity search
# ---------------------------------------------------------------------------


class FoundDocument(DocumentResponse, FoundItemBase):
    """A single result from a nearest-neighbour search over a document collection."""


"""List response for document similarity search results."""
SearchDocumentsResultListResponse = GenericListResponse[FoundDocument]


"""Request type for document similarity search."""
SearchDocumentsRequest = GenericSearchRequest[DocumentListFilter, DocumentSortField]


__all__ = [
    "FoundItemBase",
    "RRF_K",
    "QueryBase",
    "EntitySearchQuery",
    "EntityAnnotation",
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
