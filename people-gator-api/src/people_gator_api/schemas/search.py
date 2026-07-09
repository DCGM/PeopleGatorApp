"""
Pydantic schemas for search and search endpoints.

Search now returns identity and
evidence-level results keyed by ``AnnotationType``.  Search profiles remain
reusable multi-modality configurations.
"""
from pydantic import Field, BaseModel
import uuid


from people_gator_api.models.enums import AnnotationType

# ---------------------------------------------------------------------------
# Search signal contribution schemas
# ---------------------------------------------------------------------------

class SearchSignalContribution(BaseModel):
    """Per-modality score breakdown for a search result."""
    score: float
    normalised_score: float
    weight: float


class SearchIdentityResult(BaseModel):
    """An identity search result — an identity with a combined score.

    ``included_annotations`` summarises which annotations contributed to the
    identity's current view (those with an ``include`` consensus).
    """
    result_type: str = "identity"
    identity_id: uuid.UUID
    score: float
    signal_contributions: dict[AnnotationType, SearchSignalContribution]


class SearchAnnotationResult(BaseModel):
    """An annotation-level search result: a single matched annotation."""
    result_type: AnnotationType
    annotation_id: uuid.UUID
    source_id: uuid.UUID
    score: float
    signal_contributions: dict[AnnotationType, SearchSignalContribution]

# ---------------------------------------------------------------------------
# Search request and response schemas
# ---------------------------------------------------------------------------

class SearchQuery(BaseModel):
    """Typed query signals the caller wants to find matches for."""
    annotation_ids: list[uuid.UUID] | None = None
    reference_identity_id: uuid.UUID | None = None

class SearchFilters(BaseModel):
    """Filters applied to search results."""
    annotation_types: list[AnnotationType] = []
    source_kinds: list[str] = []
    has_face: bool | None = None
    has_authority_link: bool | None = None
    languages: list[str] = []

class SearchRequest(BaseModel):
    """Full search request (query + profile + result types + filters + pagination)."""
    query: SearchQuery
    filters: SearchFilters = Field(default_factory=SearchFilters)
    profile_id: uuid.UUID | None = None
    result_types: list[str] = Field(default_factory=lambda: ["identity"])
    limit: int = 20
    after_id: uuid.UUID | None = None


class SearchResponse(BaseModel):
    """Search results union plus facets and echo of the request."""

    total: int
    limit: int
    next_after_id: uuid.UUID | None
    results: list[SearchIdentityResult | SearchAnnotationResult]
    facets: dict[str, dict[str, int]]
    query: SearchQuery
    filters: SearchFilters
    profile_id: uuid.UUID | None

# ---------------------------------------------------------------------------
# Search facets response schema
# ---------------------------------------------------------------------------

class SearchFacetsResponse(BaseModel):
    """Facet counts returned alongside or independently of a search response."""

    annotation_types: dict[str, int]
    source_kinds: dict[str, int]
    result_types: dict[str, int]
    has_face: dict[str, int]
    has_authority_link: dict[str, int]
