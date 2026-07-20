"""Pydantic schemas for search and search endpoints."""

import uuid

from pydantic import AliasChoices, BaseModel, Field

from people_gator_api.schemas.enums import AnnotationType


class SearchSignalContribution(BaseModel):
    """Per-modality score breakdown for a search result."""

    score: float
    normalised_score: float
    weight: float


class SearchEntityResult(BaseModel):
    """An entity search result with a combined score."""

    result_type: str = "entity"
    entity_id: uuid.UUID
    score: float
    signal_contributions: dict[AnnotationType, SearchSignalContribution]


class SearchAnnotationResult(BaseModel):
    """An annotation-level search result."""

    result_type: AnnotationType
    annotation_id: uuid.UUID
    source_id: uuid.UUID
    score: float
    signal_contributions: dict[AnnotationType, SearchSignalContribution]


class SearchQuery(BaseModel):
    """Typed query signals the caller wants to find matches for."""

    annotation_ids: list[uuid.UUID] | None = None
    reference_entity_id: uuid.UUID | None = Field(
        default=None,
        validation_alias=AliasChoices("reference_entity_id", "reference_identity_id"),
    )


class SearchFilters(BaseModel):
    """Filters applied to search results."""

    annotation_types: list[AnnotationType] = []
    source_kinds: list[str] = []
    has_face: bool | None = None
    has_authority_link: bool | None = None
    languages: list[str] = []


class SearchRequest(BaseModel):
    """Full search request payload."""

    query: SearchQuery
    filters: SearchFilters = Field(default_factory=SearchFilters)
    profile_id: uuid.UUID | None = None
    result_types: list[str] = Field(default_factory=lambda: ["entity"])
    limit: int = 20
    after_id: uuid.UUID | None = None


class SearchResponse(BaseModel):
    """Search results union plus facets and request echo."""

    total: int
    limit: int
    next_after_id: uuid.UUID | None
    results: list[SearchEntityResult | SearchAnnotationResult]
    facets: dict[str, dict[str, int]]
    query: SearchQuery
    filters: SearchFilters
    profile_id: uuid.UUID | None


class SearchFacetsResponse(BaseModel):
    """Facet counts returned alongside search results."""

    annotation_types: dict[str, int]
    source_kinds: dict[str, int]
    result_types: dict[str, int]
    has_face: dict[str, int]
    has_authority_link: dict[str, int]

