import uuid

from pydantic import BaseModel, Field

from people_gator_api.db.models.enums import ClusterRole, EvidenceType, ProviderType


class SearchSignalContribution(BaseModel):
    raw_score: float
    normalised_score: float
    weight: float
    top_evidence_id: uuid.UUID | None


class SearchClusterMembersSummaryEntry(BaseModel):
    total: int


class SearchClusterResult(BaseModel):
    result_type: str = "cluster"
    cluster_id: uuid.UUID
    head_version_id: uuid.UUID | None
    cluster_role: ClusterRole | None
    score: float
    signal_contributions: dict[EvidenceType, SearchSignalContribution]
    members: dict[EvidenceType, SearchClusterMembersSummaryEntry]


class SearchEvidenceResult(BaseModel):
    result_type: EvidenceType
    evidence_id: uuid.UUID
    evidence_version_id: uuid.UUID
    source_id: uuid.UUID
    score: float
    signal_contributions: dict[EvidenceType, SearchSignalContribution]
    cluster_memberships: SearchClusterMembersSummaryEntry


class SearchQuery(BaseModel):
    names: list[str] | None = None
    texts: list[str] | None = None
    evidence_ids: list[uuid.UUID] | None = None
    reference_cluster_id: uuid.UUID | None = None


class SearchFilters(BaseModel):
    cluster_roles: list[ClusterRole] = []
    provider: list[ProviderType] = []
    has_face: bool | None = None
    has_authority_link: bool | None = None
    languages: list[str] = []


class SearchRequest(BaseModel):
    query: SearchQuery
    profile_id: uuid.UUID | None = None
    result_types: list[str] = Field(default_factory=lambda: ["cluster"])
    filters: SearchFilters = Field(default_factory=SearchFilters)
    limit: int = 20
    after_id: uuid.UUID | None = None
    save: bool = False


class SearchResponse(BaseModel):
    total: int
    limit: int
    next_after_id: uuid.UUID | None
    results: list[SearchClusterResult | SearchEvidenceResult]
    facets: dict[str, dict[str, int]]
    query: SearchQuery
    filters: SearchFilters
    profile_id: uuid.UUID | None
    search_cluster_id: uuid.UUID | None


class SearchFacetsResponse(BaseModel):
    cluster_roles: dict[str, int]
    provider: dict[str, int]
    result_types: dict[str, int]
    evidence_types: dict[str, int]
    has_face: dict[str, int]
    has_authority_link: dict[str, int]


class SearchProfileModalityIn(BaseModel):
    evidence_type: EvidenceType
    weight: float
    model_id: uuid.UUID | None = None
    enabled: bool = True
    min_confidence: float | None = None


class SearchProfileCreateRequest(BaseModel):
    profile_name: str
    description: str | None = None
    is_public: bool = False
    modalities: list[SearchProfileModalityIn]


class SearchProfileUpdateRequest(BaseModel):
    profile_name: str | None = None
    description: str | None = None
    is_public: bool | None = None
    modalities: list[SearchProfileModalityIn] | None = None


class SearchProfileCloneRequest(BaseModel):
    profile_name: str | None = None


class SearchProfileModalityOut(BaseModel):
    evidence_type: EvidenceType
    weight: float
    model_id: uuid.UUID | None
    enabled: bool
    min_confidence: float | None


class SearchProfileResponse(BaseModel):
    profile_id: uuid.UUID
    profile_name: str
    description: str | None
    owner_id: uuid.UUID | None
    is_public: bool
    is_system: bool
    modalities: list[SearchProfileModalityOut]
